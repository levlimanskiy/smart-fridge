import re
import json
import openai
import streamlit as st
import requests
import time

### ПРОМПТЫ
 
NORMALIZATION_PROMPT_1 = """
Ты помощник, который нормализует названия продуктов из российских кассовых чеков.
Тебе дан список сырых названий позиций. Для каждой позиции верни JSON-объект со следующими полями:
- "name": короткое понятное название на русском (без бренда, без веса/объёма), например "Молоко", "Куриное филе"

- "category": одна из категорий: «Мясо», «Птица», «Рыба», «Морепродукты», «Молочное», «Яйца», «Овощи», «Фрукты», 
«Крупы», «Хлеб и выпечка», «Кондитерские изделия», «Орехи и сухофрукты», «Масла и соусы», «Напитки»,
«Консервация», «Полуфабрикаты», «Другое»

- "days": целое число — базовый срок хранения в днях (курица ~4, молоко ~7, сыр ~14, хлеб ~3, яйца ~21, овощи ~7)

- "q": числовое значение количества товара (только число, без единиц). Например: 2, 200, 450
- "unit": единица измерения. Одно из: "шт", "г", "кг", "мл", "л". Если неизвестно — "шт"

- "emoji": один подходящий эмодзи

Верни ТОЛЬКО валидный JSON-массив. Никакого текста до или после. Пример:
[{{"name":"Молоко","category":"Молочное","days":7,"q":950,"unit":"мл","emoji":"🥛"}}]

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
- "ingredients": список ингредиентов из холодильника которые используются (массив строк)
- "commentary": 2-3 предложения о пользе блюда (витамины, минералы, органика, белки и тд)
- "emoji": один подходящий эмодзи

Верни ТОЛЬКО валидный JSON-массив из 5 объектов. Никакого текста до или после. Пример:
[{{
  "title": "Омлет с помидорами",
  "title_en": "Omelette with tomatoes",
  "time": 10,
  "ingredients": ["яйца", "помидоры", "молоко"],
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
        text = self._call_model(prompt, max_tokens=3000)
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
        text = self._call_model(prompt, max_tokens=4000)
        if not text:
            return []

        recipes = self._parse_json(text)
        if not recipes:
            return []

        for recipe in recipes:
            recipe["image_url"] = self._get_image(recipe.get("title_en", ""))
            time.sleep(0.3)

        return recipes