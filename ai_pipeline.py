import re
import json
import openai
import streamlit as st
import requests
import time

### ПРОМПТЫ
 
NORMALIZATION_PROMPT_1 = """
Ты — специализированный ИИ-модуль для нормализации позиций из российских кассовых чеков.
Твоя задача — преобразовать сырые строки чека в структурированный JSON-массив.

Входные данные могут быть двух типов:
1. "<название>, <единица> - <цена> руб. x <кол-во> шт."
2. "<название и вес/объем порции> - <цена> руб. x <кол-во> шт."

Для каждой позиции сформируй JSON-объект со следующими полями:
- "name": короткое, понятное название продукта на русском языке в начальной форме (например: "Петрушка", "Куриное филе", "Гречневая крупа", "Йогурт"). Обязательно удаляй бренды (Global Village, Домик в деревне), технические символы, даты и явное указание веса из этого поля.
- "category": строго одно значение из списка: «Мясо», «Птица», «Рыба», «Морепродукты», «Молочное», «Яйца», «Овощи», «Фрукты», «Крупы», «Хлеб и выпечка», «Кондитерские изделия», «Орехи и сухофрукты», «Масла и соусы», «Напитки», «Консервация», «Полуфабрикаты», «Другое».
- "days": целое число — базовый срок хранения продукта в днях (ориентиры: птица/мясо ~4, зелень ~5, молоко ~7, сыр ~14, хлеб ~3, яйца ~21, крупы ~365).
- "q": числовое значение количества/объема одной порции ИЛИ количества штук, если вес не указан. Не перемножай значения между собой! Если указано "Йогурт 150г ... x 3 шт", запиши сюда 150. Если вес не указан ("Батон ... x 2 шт"), запиши сюда 2.
- "unit": единица измерения для поля "q". Строго одно из: "шт", "г", "кг", "мл", "л". Если в названии есть "100г" -> "г", если "0.95кг" -> "кг". Если веса/объема в названии нет -> "шт".
- "package_count": целое число. Количество купленных упаковок/штук из конца строки (после знака 'x'). Если не указано — 1.
- "price": цена за 1 шт/упаковку в рублях (дробное число). Извлеки из суффикса <цена>.
- "emoji": один наиболее подходящий по смыслу эмодзи.

Выведи ТОЛЬКО валидный JSON-массив объектов. Не добавляй никаких пояснений, форматирования markdown (```json) или текста до и после структуры.

Примеры входных строк и ожидаемых ответов:

Пример 1:
"Петрушка Global Village 100г - 119.99 руб. x 2 шт."
Ответ 1:
[{{"name": "Петрушка", "category": "Овощи", "days": 5, "q": 100, "unit": "г", "package_count": 2, "price": 119.99, "emoji": "🌿"}}]

Пример 2:
"Мясо бедра индейки в маринаде \"Чесночный\",кг — 937.00 руб. x 0.95 шт."
Ответ 2:
[{{"name": "Индейка бедро", "category": "Птица", "days": 4, "q": 1, "unit": "кг", "package_count": 0.95, "price": 937.00, "emoji": "🍗"}}]

Позиции из чека:
{items}
"""

RECIPE_PROMPT  = """
Ты опытный шеф-повар и диетолог. Тебе дан список продуктов из холодильника пользователя.
Продукты, помеченные как "⚠️ истекает", нужно использовать в первую очередь.

Предложи ровно 5 рецептов, которые можно приготовить из этих продуктов.
Для каждого рецепта верни JSON-объект со следующими полями:
- "title": название блюда на русском
- "title_en": название блюда на английском (для поиска картинок)
- "time": время приготовления в минутах (целое число)
- "ingredients": массив строк. Каждый элемент должен строго содержать название используемого ингредиента и его необходимое количество для рецепта в формате: "<название>: <кол-во> <ед. изм.>" (например: "петрушка: 10 г", "томаты черри: 150 г", "огурец: 2 шт"). Рассчитывай количество исходя из того, сколько реально нужно на порцию для этого блюда.
- "commentary": 2-3 предложения о пользе блюда (витамины, минералы, органика, белки и тд)
- "emoji": один подходящий эмодзи

Верни ТОЛЬКО валидный JSON-массив из 5 объектов. Никакого текста до или после. Пример:
[{{
  "title": "Омлет с помидорами",
  "title_en": "Omelette with tomatoes",
  "time": 10,
  "ingredients": ["яйца: 2 шт", "томаты черри: 100 г", "молоко: 50 мл"],
  "commentary": "Богат белком и витамином C. Помидоры содержат ликопин — мощный антиоксидант. Лёгкое и питательное блюдо для начала дня.",
  "emoji": "🍳"
}}]

Продукты в холодильнике:
{items}
"""

### НАША ЧУДО-МОДЕЛЬКА

class AIModel:
    def __init__(self, api_key: str, folder_id: str, model_uri: str, unsplash_key: str | None=None):
        self.api    = api_key
        self.folder = folder_id
        self.model  = model_uri
        self.unsplash_key = unsplash_key

    def _get_client(self) -> openai.OpenAI:
        return openai.OpenAI(
            api_key=self.api,
            project=self.folder,
            base_url="https://ai.api.cloud.yandex.net/v1"
        )

    def _call_model(self, prompt: str, max_tokens: int = 5000) -> str | None:

        client = self._get_client()

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                st.error(f"Модель не вернула ответ. Причина: {response.choices[0].finish_reason}")
                return None
            return content.strip()
        except Exception as e:
            st.error(f"Ошибка модели: {e}")
            return None

    def _parse_json(self, text: str) -> list[dict] | None:

        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            st.error(f"Ошибка разбора JSON: {e}")
            return None

    def normalize(self, raw_items: list[str]) -> list[dict]:
        food_items = [i for i in raw_items if not any(
            skip in i.lower() for skip in ["доставка", "упаковка", "сборка", "пакет"]
        )]

        prompt = NORMALIZATION_PROMPT_1.format(items="\n".join(f"- {i}" for i in food_items))
        text = self._call_model(prompt, max_tokens=5000)
        if not text:
            return []

        result = self._parse_json(text)
        return result if result else []

    def _get_image(self, title: str) -> str | None:
        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": title, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {self.unsplash_key}"},
                timeout=5
            )
            data = resp.json()
            return data["results"][0]["urls"]["regular"]
        except Exception:
            return None
        
    
    def suggest_recipes(self, products: list[dict]) -> list[dict]:

        item_lines = []

        for p in products:
            flag = " ⚠️ истекает" if p.get("days", 99) <= 2 else ""
            item_lines.append(f"- {p['name']} ({p['q']} {p['unit']}){flag}")

        prompt = RECIPE_PROMPT.format(items="\n".join(item_lines))
        text = self._call_model(prompt, max_tokens=6000)
        if not text:
            return []

        recipes = self._parse_json(text)
        if not recipes:
            return []

        for recipe in recipes:
            recipe["image_url"] = self._get_image(recipe.get("title_en", ""))
            time.sleep(0.3)

        return recipes