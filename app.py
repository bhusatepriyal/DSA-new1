import streamlit as st
import pandas as pd
from collections import deque

# --- SAFETY CHECK: Optional Graphviz ---
try:
    import graphviz
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False

# =========================================
# 🎨 UI CONFIGURATION & STYLING
# =========================================
st.set_page_config(
    page_title="Pro Bracket Manager",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for "Cards", Metrics, and Tabs
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #0e1117;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #262730;
        border-bottom: 2px solid #ff4b4b;
    }
    div.stButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
        height: 3em;
    }
    .match-card {
        background-color: #262730;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #464b5d;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .match-card h3 {
        margin: 0;
        color: #ff4b4b;
        font-size: 1.1em;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .match-card h1 {
        margin: 10px 0;
        font-size: 2.2em;
    }
    .vs {
        color: #a6a9b6;
        font-size: 0.6em;
        vertical-align: middle;
    }
</style>
""", unsafe_allow_html=True)

# =========================================
# 🧠 PART 1: CORE DATA STRUCTURES (FAITHFUL C PORT)
# =========================================

class Player:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.wins = 0
        self.losses = 0
        self.score_for = 0
        self.score_against = 0
    def get_pd(self): return self.score_for - self.score_against
    def __repr__(self): return f"<Player {self.id}: {self.name}>"

class Match:
    def __init__(self, match_id, round_num=0):
        self.match_id = match_id
        self.player1 = None
        self.player2 = None
        self.winner = None
        self.round = round_num
        self.is_from_losers = False
        self.is_leaf = False
        self.player1_score = 0
        self.player2_score = 0

class MatchNode:
    def __init__(self, match):
        self.match = match
        self.left = None
        self.right = None

class QueueNode:
    def __init__(self, match_ptr):
        self.match_ptr = match_ptr
        self.next = None

class Queue:
    def __init__(self):
        self.front = None
        self.rear = None
    def is_empty(self): return self.front is None
    def enqueue(self, match_ptr):
        if not match_ptr: return
        n = QueueNode(match_ptr)
        if self.rear is None: self.front = self.rear = n
        else:
            self.rear.next = n
            self.rear = n
    def iter_nodes(self):
        cur = self.front
        while cur:
            yield cur.match_ptr
            cur = cur.next

class AVLNode:
    def __init__(self, key, match_ptr):
        self.key = key
        self.match_ptr = match_ptr
        self.left = None
        self.right = None
        self.height = 1

# =========================================
# 💾 PART 2: GLOBAL STATE MANAGEMENT
# =========================================

def init_state():
    if 'mode' not in st.session_state: st.session_state.mode = "None"
    if 'players' not in st.session_state: st.session_state.players = []
    if 'player_map' not in st.session_state: st.session_state.player_map = {}
    if 'next_pid' not in st.session_state: st.session_state.next_pid = 1000
    if 'next_mid' not in st.session_state: st.session_state.next_mid = 100
    if 'bracket_root' not in st.session_state: st.session_state.bracket_root = None
    if 'winners_root' not in st.session_state: st.session_state.winners_root = None
    if 'match_queue' not in st.session_state: st.session_state.match_queue = Queue()
    if 'avl_root' not in st.session_state: st.session_state.avl_root = None
    if 'losers_fifo' not in st.session_state: st.session_state.losers_fifo = deque()
    if 'matches_played' not in st.session_state: st.session_state.matches_played = 0
    if 'rr_edges' not in st.session_state: st.session_state.rr_edges = 0
    if 'rr_completed' not in st.session_state: st.session_state.rr_completed = 0
    if 'rr_advance' not in st.session_state: st.session_state.rr_advance = 0

init_state()

# =========================================
# ⚙️ PART 3: CORE LOGIC (C TRANSLATION)
# =========================================

# --- AVL Utils ---
def avl_h(n): return n.height if n else 0
def avl_bal(n): return avl_h(n.left) - avl_h(n.right) if n else 0
def avl_rot_r(y):
    x = y.left; T2 = x.right; x.right = y; y.left = T2
    y.height = 1 + max(avl_h(y.left), avl_h(y.right))
    x.height = 1 + max(avl_h(x.left), avl_h(x.right))
    return x
def avl_rot_l(x):
    y = x.right; T2 = y.left; y.left = x; x.right = T2
    x.height = 1 + max(avl_h(x.left), avl_h(x.right))
    y.height = 1 + max(avl_h(y.left), avl_h(y.right))
    return y
def avl_ins(node, key, mptr):
    if not node: return AVLNode(key, mptr)
    if key < node.key: node.left = avl_ins(node.left, key, mptr)
    elif key > node.key: node.right = avl_ins(node.right, key, mptr)
    else: return node
    node.height = 1 + max(avl_h(node.left), avl_h(node.right))
    b = avl_bal(node)
    if b > 1 and key < node.left.key: return avl_rot_r(node)
    if b < -1 and key > node.right.key: return avl_rot_l(node)
    if b > 1 and key > node.left.key: node.left = avl_rot_l(node.left); return avl_rot_r(node)
    if b < -1 and key < node.right.key: node.right = avl_rot_r(node.right); return avl_rot_l(node)
    return node
def avl_find(node, key):
    if not node or node.key == key: return node
    return avl_find(node.left, key) if key < node.key else avl_find(node.right, key)

# --- Creation & Registration ---
def create_match_node(r=0):
    mid = st.session_state.next_mid
    st.session_state.next_mid += 1
    mnode = MatchNode(Match(mid, r))
    st.session_state.avl_root = avl_ins(st.session_state.avl_root, mid, mnode)
    return mnode

def register_player(name):
    if st.session_state.mode != "None": return False, "Tournament already started."
    if not name: return False, "Name cannot be empty."
    if name in st.session_state.player_map: return False, "Name already taken."
    pid = st.session_state.next_pid
    st.session_state.next_pid += 1
    p = Player(pid, name)
    st.session_state.players.append(p)
    st.session_state.player_map[name] = p
    return True, f"Registered {name} (ID: {pid})"

# --- Bracket Generation ---
def create_bracket_rec(parts, s, e):
    if s == e:
        leaf = create_match_node(1)
        leaf.match.is_leaf = True
        leaf.match.player1 = parts[s]
        return leaf
    mid = (s + e) // 2
    left = create_bracket_rec(parts, s, mid)
    right = create_bracket_rec(parts, mid + 1, e)
    parent = create_match_node()
    parent.left, parent.right = left, right
    if left.match.is_leaf and right.match.is_leaf:
        parent.match.player1 = left.match.player1
        parent.match.player2 = right.match.player1
        parent.match.round = 1
        st.session_state.match_queue.enqueue(parent)
    return parent

def fix_rounds(node, depth, max_d):
    if not node: return
    if not node.match.is_leaf: node.match.round = max_d - depth
    fix_rounds(node.left, depth + 1, max_d)
    fix_rounds(node.right, depth + 1, max_d)

def get_depth(node): return 1 + max(get_depth(node.left), get_depth(node.right)) if node else 0

def generate_ko():
    n = len(st.session_state.players)
    if n < 2: return False, "Need 2+ players."
    st.session_state.match_queue = Queue()
    root = create_bracket_rec(st.session_state.players, 0, n-1)
    fix_rounds(root, 0, get_depth(root) - (1 if get_depth(root)>1 else 0))
    st.session_state.bracket_root = root
    st.session_state.mode = "Knockout"
    return True, f"Knockout generated for {n} players."

# --- Match Updates ---
def update_match_generic(node, mid, winner, s1, s2):
    if not node: return False, None
    m = node.match
    if m.match_id == mid:
        if m.winner: return True, None # Already played
        m.winner = winner
        st.session_state.matches_played += 1
        winner.wins += 1
        loser = m.player2 if m.player1 == winner else m.player1
        if loser: loser.losses += 1
        winner.score_for += s1; winner.score_against += s2
        if loser: loser.score_for += s2; loser.score_against += s1
        m.player1_score = s1 if m.player1 == winner else s2
        m.player2_score = s2 if m.player1 == winner else s1
        return True, loser
    f, l = update_match_generic(node.left, mid, winner, s1, s2)
    if f: return True, l
    return update_match_generic(node.right, mid, winner, s1, s2)

def check_schedule(node):
    if not node or node.match.is_leaf: return
    check_schedule(node.left); check_schedule(node.right)
    if node.left and node.right and node.left.match.winner and node.right.match.winner:
        if not node.match.winner and not node.match.player1:
             node.match.player1 = node.left.match.winner
             node.match.player2 = node.right.match.winner
             st.session_state.match_queue.enqueue(node)

# =========================================
# 📊 PART 4: VISUALIZATION ENGINES
# =========================================
def draw_bracket_graphviz(root_node):
    if not root_node or not HAS_GRAPHVIZ: return None
    g = graphviz.Digraph(comment='Tournament Bracket')
    g.attr(rankdir='LR', bgcolor='transparent')
    g.attr('node', shape='box', style='filled', color='#464b5d', fontname='sans-serif', fontcolor='white')
    g.attr('edge', color='#a6a9b6')

    def add_nodes(node):
        if not node: return
        m = node.match
        p1 = m.player1.name if m.player1 else "?"
        p2 = m.player2.name if m.player2 else "?"
        label = f"M{m.match_id}\n{p1} vs {p2}"
        fill = '#262730'
        if m.winner:
            fill = '#0e3311' # Dark green for winner
            label += f"\n🏆 {m.winner.name}"
        elif m.player1 and m.player2:
             fill = '#5e3c0a' # Dark orange for ready

        g.node(str(m.match_id), label=label, fillcolor=fill)
        if node.left:
            add_nodes(node.left)
            g.edge(str(node.left.match.match_id), str(m.match_id))
        if node.right:
            add_nodes(node.right)
            g.edge(str(node.right.match.match_id), str(m.match_id))
    add_nodes(root_node)
    return g

def get_bracket_text(node, level=0, prefix="Root: "):
    if not node: return ""
    m = node.match
    p1 = m.player1.name if m.player1 else "TBD"
    p2 = m.player2.name if m.player2 else "TBD"
    win = f" -> Winner: {m.winner.name}" if m.winner else ""
    indent = "    " * level
    text = f"{indent}{prefix}[M{m.match_id}] {p1} vs {p2}{win}\n"
    text += get_bracket_text(node.left, level + 1, "L--- ")
    text += get_bracket_text(node.right, level + 1, "R--- ")
    return text

# =========================================
# 🚀 PART 5: MODERN MAIN UI
# =========================================

# --- Sidebar Dashboard ---
with st.sidebar:
    st.title("🎮 Command Center")
    st.metric("Tournament Mode", st.session_state.mode)
    c1, c2 = st.columns(2)
    c1.metric("Players", len(st.session_state.players))
    c2.metric("Matches Done", st.session_state.matches_played)
    st.divider()
    if st.button("⚠️ RESET SYSTEM", type="primary"):
        st.session_state.clear()
        st.rerun()

# --- Main Tabs ---
tab_setup, tab_play, tab_bracket, tab_stats = st.tabs(["🛠️ Setup", "⚔️ Arena", "🕸️ Bracket", "📈 Leaderboard"])

# === TAB 1: SETUP ===
with tab_setup:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("New Player Registry")
        with st.form("reg_form", clear_on_submit=True):
            p_name = st.text_input("Codename", placeholder="Enter name...")
            if st.form_submit_button("Register Player"):
                ok, msg = register_player(p_name)
                if ok: st.toast(msg, icon="✅")
                else: st.error(msg)
        
        st.subheader("Initialization")
        ttype = st.selectbox("Format", ["Knockout"])
        if st.button("🚀 GENERATE BRACKET", disabled=(st.session_state.mode != "None")):
             if ttype == "Knockout":
                 ok, msg = generate_ko()
                 if ok: 
                     st.balloons()
                     st.success(msg)
                     st.rerun()
                 else: st.error(msg)
    with c2:
        st.subheader("Roster")
        if st.session_state.players:
            st.dataframe(
                pd.DataFrame([{"ID": p.id, "Name": p.name} for p in st.session_state.players]),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("Awaiting registrations...")

# === TAB 2: ARENA (PLAY) ===
with tab_play:
    st.header("⚔️ Active Match Arena")
    playable = []
    for mnode in st.session_state.match_queue.iter_nodes():
        m = mnode.match
        if m.player1 and m.player2 and not m.winner:
            playable.append(mnode)
            
    if not playable:
        if st.session_state.mode == "None": st.warning("Tournament not started.")
        elif st.session_state.bracket_root and st.session_state.bracket_root.match.winner:
             st.success(f"🎉 TOURNAMENT COMPLETE! Champion: {st.session_state.bracket_root.match.winner.name}")
        else: st.info("Waiting for previous rounds to finish...")
    else:
        # Match Card UI
        active_node = playable[0]
        m = active_node.match
        st.markdown(f"""
        <div class="match-card">
            <h3>MATCH {m.match_id} • ROUND {m.round}</h3>
            <h1>{m.player1.name} <span class="vs">VS</span> {m.player2.name}</h1>
        </div>
        """, unsafe_allow_html=True)

        with st.form("match_result"):
            c1, c2, c3 = st.columns([2,1,1])
            winner_name = c1.radio("Select Winner", [m.player1.name, m.player2.name], horizontal=True)
            s1 = c2.number_input(f"{m.player1.name} Score", min_value=0, step=1)
            s2 = c3.number_input(f"{m.player2.name} Score", min_value=0, step=1)
            if st.form_submit_button("CONFIRM RESULT"):
                w_obj = st.session_state.player_map[winner_name]
                ok, _ = update_match_generic(st.session_state.bracket_root, m.match_id, w_obj, s1, s2)
                if ok:
                    check_schedule(st.session_state.bracket_root)
                    st.toast(f"Match {m.match_id} updated!", icon="🔥")
                    st.rerun()
        
        if len(playable) > 1:
            with st.expander(f"View {len(playable)-1} Other Pending Matches"):
                 for pending in playable[1:]:
                     pm = pending.match
                     st.write(f"**M{pm.match_id}**: {pm.player1.name} vs {pm.player2.name}")

# === TAB 3: BRACKET ===
with tab_bracket:
    st.header("🕸️ Tournament Tree")
    if st.session_state.bracket_root:
        if HAS_GRAPHVIZ and st.session_state.mode == "Knockout":
            try:
                graph = draw_bracket_graphviz(st.session_state.bracket_root)
                st.graphviz_chart(graph, use_container_width=True)
            except Exception as e:
                st.warning(f"Visual bracket failed to render. Falling back to text. ({e})")
                st.text(get_bracket_text(st.session_state.bracket_root))
        else:
            st.text(get_bracket_text(st.session_state.bracket_root))
            if not HAS_GRAPHVIZ: st.caption("Install 'graphviz' for visual trees.")
    else:
        st.info("Bracket not generated.")

# === TAB 4: STATS ===
with tab_stats:
    st.header("📈 Live Leaderboard")
    if st.session_state.players:
        sorted_p = sorted(st.session_state.players, key=lambda x: (x.wins, x.get_pd()), reverse=True)
        st.dataframe(
            pd.DataFrame([{"Rank": i+1, "Name": p.name, "W": p.wins, "L": p.losses, "PD": p.get_pd()} for i, p in enumerate(sorted_p)]),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("No data yet.")