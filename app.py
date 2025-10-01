import streamlit as st
from views import analytics, reviews

st.set_page_config(page_title="HDBLens", page_icon="🏠", layout="wide")

st.sidebar.title("📌 Navigation")
page = st.sidebar.radio("Go to", ["Home", "Analytics", "Reviews"], index=0)

match page:
    case "Home":
        st.title("🏠 Welcome to HDBLens")
        st.subheader("Smarter Insights for Every Homebuyer")
        st.markdown("""
        HDBLens is your one-stop platform for exploring **HDB resale prices** in Singapore.

        This app will help you:
        - 📊 Discover trends in resale prices
        - 🏘️ Compare across towns and flat types
        - ✍️ Share and read reviews from other users

        ---
        """)
        st.image("assets/home_image.png", caption="HDB Resale Flats in Singapore", use_container_width=True)

    case "Analytics":
        analytics.render()

    case "Reviews":
        reviews.render()

    case _:
        st.error("Page not found")

