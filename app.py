import streamlit as st
from views import analytics, reviews, home
from db_config import init_sql_db, init_mongo

st.set_page_config(page_title="HDBLens", page_icon="🏠", layout="wide")

def _alert(ok: bool, msg: str):
    (st.success if ok else st.error)(msg)

# Initialize both databases (only creates tables/import data on 1st time)
ok_pg, msg_pg = init_sql_db()
ok_mg, msg_mg = init_mongo()

with st.sidebar:
    st.subheader("System Status")
    _alert(ok_pg, msg_pg)
    _alert(ok_mg, msg_mg)

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Home", "Analytics", "Reviews"], index=0)

match page:
    case "Home":
        st.title("Welcome to HDBLens")
        st.subheader("Smarter Insights for Every Homebuyer")
        st.markdown("""
        HDBLens is your one-stop platform for exploring **HDB resale prices** in Singapore.

        This app will help you:
        - Discover trends in resale prices
        - Compare across towns and flat types
        - Share and read reviews from other users

        ---
        """)
        home.render()

    case "Analytics":
        analytics.render()

    case "Reviews":
        reviews.render()

    case _:
        st.error("Page not found")

