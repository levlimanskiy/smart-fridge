import streamlit as st
from PIL import Image
from qr_reader import QRReader
from ai_pipeline import AIModel

### ФУНКЦИИ-ПОМОЩНИКИ

def expiry_badge(days: int) -> str:
    if days <= 2:
        return f'<span class="badge badge-danger">🔴 {days} д.</span>'
    if days <= 5:
        return f'<span class="badge badge-warn">🟡 {days} д.</span>'
    return f'<span class="badge badge-ok">🟢 {days} д.</span>'

def match_recipes(products):
    names = " ".join(p["name"].lower() for p in products)
    matched = [r for r in RECIPE_DB if any(t in names for t in r["tags"])]
    return matched[:3] if matched else RECIPE_DB[:2]

### CONFIG СТРАНИЦЫ

st.set_page_config(
    page_title="SmartFridge & Budget",
    page_icon="🥗",
    layout="centered",
)

### ВЕРСТКА CSS

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Syne', sans-serif !important; }

.metric-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.metric-card {
    flex: 1; min-width: 140px;
    background: white; border-radius: 18px;
    padding: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.07);
}
.metric-icon { font-size: 22px; margin-bottom: 6px; }
.metric-value { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 800; }
.metric-label { font-size: 11px; color: #64748b; margin-top: 3px; line-height: 1.4; }

.product-row {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px; border-radius: 14px;
    background: white; margin-bottom: 8px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}
.product-emoji { font-size: 26px; }
.product-name { font-weight: 600; font-size: 14px; flex: 1; }
.product-cat  { font-size: 11px; color: #64748b; }

.badge {
    font-size: 10px; font-weight: 700; padding: 3px 9px;
    border-radius: 20px; white-space: nowrap;
}
.badge-ok     { background:#dcfce7; color:#15803d; }
.badge-warn   { background:#fef3c7; color:#92400e; }
.badge-danger { background:#fee2e2; color:#991b1b; }

.recipe-card {
    background: linear-gradient(135deg,#f0fdf4,#dcfce7);
    border: 1.5px solid #bbf7d0; border-radius: 18px;
    padding: 16px; margin-bottom: 12px;
}
.recipe-title { font-family:'Syne',sans-serif; font-size:16px; font-weight:700; }
.recipe-meta  { font-size:12px; color:#374151; margin-top:6px; }
.recipe-save  {
    background:#dcfce7; border-radius:10px; padding:8px 12px;
    font-size:12px; font-weight:600; color:#15803d;
    margin-top:10px; display:inline-block;
}

.progress-wrap { margin-bottom: 12px; }
.progress-label { display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px; }
</style>
""", unsafe_allow_html=True)

### ФЕЙКОВАЯ БД

INITIAL_PRODUCTS = []

CATEGORIES = []
CAT_EMOJI  = {}
RECIPE_DB = []


### ОПЕРАТИВНАЯ ПАМЯТЬ САЙТА

if "products" not in st.session_state:
    st.session_state.products = [p.copy() for p in INITIAL_PRODUCTS]
if "next_id" not in st.session_state:
    st.session_state.next_id = 1
if "recipes" not in st.session_state:
    st.session_state.recipes = []
if "finance" not in st.session_state:
    st.session_state["finance"] = {
        "total_spent":    0.0,
        "receipts_count": 0,
        "cooked_count":   0,
    }
### ЗАГОЛОВОК

st.markdown("## 🥗 SmartFridge & Budget")
st.caption("ИИ-шеф и трекер холодильника")
st.divider()

tab_fridge, tab_chef, tab_dash = st.tabs(["🧊 Холодильник", "👨‍🍳 ИИ-Шеф", "📊 Бюджет"])

# ════════════════════════════════════════════════════════════════════════════
# ЧАСТЬ 1: ХОЛОДИЛЬНИК
# ════════════════════════════════════════════════════════════════════════════
with tab_fridge:
    st.subheader(f"🧊 Холодильник ({len(st.session_state.products)} продуктов)")

    if not st.session_state.products:
        st.info("Холодильник пуст — добавьте продукты ниже!")
    else:
        to_remove = None
        for p in st.session_state.products:
            col_emoji, col_info, col_badge, q, unit, col_trash = st.columns(6)
            with col_emoji:
                st.markdown(f"<p style='font-size:24px;margin:6px 0'>{p['emoji']}</p>", unsafe_allow_html=True)

            with col_info:
                st.markdown(f"**{p['name']}**  \n<span style='font-size:11px;color:#64748b'>{p['category']}</span>", unsafe_allow_html=True)

            with col_badge:
                st.markdown(expiry_badge(p["days"]), unsafe_allow_html=True)

            with q:
                st.markdown(f"<p style='font-size:24px;margin:6px 0'>{p['q']}</p>", unsafe_allow_html=True)

            with unit:
                st.markdown(f"<p style='font-size:24px;margin:6px 0'>{p['unit']}</p>", unsafe_allow_html=True)

            with col_trash:
                if st.button("🗑", key=f"trash_{p['id']}", help="Выбросить"):
                    st.session_state[f"trashing_{p['id']}"] = True
                
                if st.session_state.get(f"trashing_{p['id']}"):
                    amount = st.number_input(
                        f"Сколько выбросить? (осталось {p['q']} {p['unit']})",
                        min_value=0.0,
                        max_value=float(p['q']),
                        value=float(p['q']),
                        step=1.0,
                        key=f"trash_amount_{p['id']}"
                    )
                    col_confirm, col_cancel = st.columns(2)
                    with col_confirm:
                        if st.button("✅ ", key=f"trash_confirm_{p['id']}"):
                            new_q = p['q'] - amount
                            if new_q <= 0:
                                to_remove = p['id']
                            else:
                                p['q'] = new_q
                                del st.session_state[f"trashing_{p['id']}"]
                                st.rerun()
                    with col_cancel:
                        if st.button("✕", key=f"trash_cancel_{p['id']}"):
                            del st.session_state[f"trashing_{p['id']}"]
                            st.rerun()

                    if to_remove is not None:
                        st.session_state.products = [p for p in st.session_state.products if p["id"] != to_remove]
                        st.rerun()

    st.divider()

    with st.expander("📷 Сканировать чек по QR-коду"):
        st.caption("Сфотографируйте QR-код внизу кассового чека и загрузите изображение. " \
        "Также можно прикрепить изображение QR-кода из электронного чека (оно обычно внизу).")
        qr_file = st.file_uploader(
            "Загрузить фото QR-кода", type=["png", "jpg", "jpeg", "webp"],
            key="qr_upload", label_visibility="collapsed"
        )

        if qr_file:
            img = Image.open(qr_file)
            st.image(img, caption="Загруженное изображение", width=220)

            qr_api = st.secrets.receipts.api

            api_ai = st.secrets.ai.YANDEX_API_KEY
            folder_ai = st.secrets.ai.YANDEX_FOLDER_ID
            uri_ai = st.secrets.ai.YANDEX_MODEL_URI
            
            reader = QRReader(qr_file, qr_api)
            qr_data = reader.decode_qr()

            model = AIModel(api_ai, folder_ai, uri_ai)

            if qr_data == []:
                st.error("QR-код не найден. Попробуйте более чёткое фото.")
            else:
                st.success(f"✅ QR считан")
                st.code(qr_data, language=None)

                if st.button("🧾 Получить и разобрать чек", use_container_width=True, type="primary"):
                    with st.spinner("Запрашиваю данные чека в ФНС..."):
                        raw_items = reader.get_receipt_info()

                    st.info(f"Получено {len(raw_items)} позиций. Нормализую через Yandex AI...")

                    with st.spinner("Yandex AI обрабатывает названия..."):
                        normalized = model.normalize(raw_items)

                    if normalized: 
                        added = 0

                        receipt_total = sum(
                            item.get("price", 0) * item.get("package_count", 1)
                            for item in normalized
                            if item.get("price") is not None
                        )
                        st.session_state["finance"]["total_spent"] += receipt_total
                        st.session_state["finance"]["receipts_count"] += 1

                        for item in normalized:
                            existing = [p["name"].lower() for p in st.session_state.products]
                            if item.get("name", "").lower() not in existing:
                                # добавляем продукт
                                st.session_state.products.append({
                                    "id": st.session_state.next_id,
                                    "name": item.get("name", "Неизвестно"),
                                    "emoji": item.get("emoji", "📦"),
                                    "category": item.get("category", "Другое"),
                                    "q": item.get("q", 1)*item.get("package_count", 1),
                                    "unit": item.get("unit", "шт"),
                                    "days": item.get("days", 5),
                                    "price": item.get('price', 0)
                                })
                                st.session_state.next_id += 1
                                added += 1
                            else:
                                # иначе прибавляем количество просто
                                for p in st.session_state.products:
                                    if p["name"].lower() == item.get("name", "").lower():
                                        p["q"] += item.get("q", 1)
                                        break


                        st.success(f"✅ Добавлено {added} новых продуктов в холодильник!")
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# ЧАСТЬ 2 - ИИ ШЕФ
# ════════════════════════════════════════════════════════════════════════════
with tab_chef:
    if st.button("✨ Сгенерировать рецепты из остатков", use_container_width=True, type="primary"):
        
        api_ai = st.secrets.ai.YANDEX_API_KEY
        folder_ai = st.secrets.ai.YANDEX_FOLDER_ID
        uri_ai = st.secrets.ai.YANDEX_MODEL_URI
        unsplash_api = st.secrets.img.UNSPLASH_API

        model = AIModel(api_ai, folder_ai, uri_ai, unsplash_api)

        with st.spinner("ИИ-Шеф думает..."):
            st.session_state.recipes = model.suggest_recipes(st.session_state.products)

    for r in st.session_state.recipes:
        col_img, col_info = st.columns([1, 2])
        with col_img:
            if r.get("image_url"):
                st.image(r["image_url"], use_container_width=True)
            else:
                st.markdown(f"<div style='font-size:64px;text-align:center'>{r['emoji']}</div>", unsafe_allow_html=True)
        with col_info:
            st.markdown(f"### {r['emoji']} {r['title']}")
            st.caption(f"⏱ {r['time']} мин · 🥕 {', '.join(r['ingredients'])}")
            st.info(r["commentary"])
                

# ════════════════════════════════════════════════════════════════════════════
# ЧАСТЬ 3 - ФИНАНСЫ
# ════════════════════════════════════════════════════════════════════════════
with tab_dash:
    st.subheader("📊 Анти-бухгалтерия")

    f = st.session_state["finance"]
    expiring = [p for p in st.session_state.products if p.get("days", 99) <= 2]

    potential_waste = sum(
        p["price"] * p["q"]
        for p in expiring
        if p.get("price") is not None
    )
    
    fridge_value = sum(
    p["price"] * p["q"]
    for p in st.session_state.products
    if p.get("price") is not None
    )

    col1, col2, col4 = st.columns(3)
    col1.metric(
    "💰 Стоимость холодильника",
    f"{fridge_value:.2f} ₽" if fridge_value > 0 else "н/д",
    f"{len(st.session_state.products)} продуктов"
    )
    col2.metric(
        "🧾 Потрачено на продукты",
        f"{f['total_spent']:.2f} ₽" if f["total_spent"] > 0 else "н/д",
        f"{f['receipts_count']} чеков"
    )
    col4.metric(
        "📦 В холодильнике",
        len(st.session_state.products),
        "продуктов"
    )

    st.divider()

    st.markdown("**Состав холодильника по категориям**")

    from collections import defaultdict
    cat_totals = defaultdict(float)
    for p in st.session_state.products:
        if p.get("price") is not None:
            cat_totals[p["category"]] += p["price"] * p["q"]

    total_cat = sum(cat_totals.values())

    if total_cat > 0:
        for cat, amount in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
            pct = amount / total_cat
            col_label, col_bar, col_val = st.columns([2, 3, 1])
            with col_label:
                st.caption(cat)
            with col_bar:
                st.progress(pct)
            with col_val:
                st.caption(f"{amount:.0f} ₽")
    else:
        st.info("Отсканируйте чек, чтобы увидеть разбивку по категориям.")

    if expiring:
        st.divider()
        st.error(f"⚠️ **{len(expiring)} продукта истекают в ближайшие 2 дня!**")
        for p in expiring:
            price_str = f" — {p['price'] * p['q']:.2f} ₽" if p.get("price") else ""
            st.markdown(f"- {p['emoji']} **{p['name']}** ({p['q']} {p['unit']}){price_str} — {p['days']} д.")