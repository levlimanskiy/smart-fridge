import requests
import numpy as np
import cv2
from PIL import Image
import streamlit as st
import re

class QRReader:
    def __init__(self, qr_file, api: str):
        self.img = Image.open(qr_file)
        self.api = api
        self.qr_string: str | None = None


    def decode_qr(self) -> str | None:
        img_array = np.array(self.img)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img_array) 
        self.qr_string = data if data else None
        return self.qr_string

    def get_receipt_info(self) -> list[str]:
        if not self.decode_qr():
            st.error("QR-код не распознан. Попробуйте более чёткое фото.")  
            return []
        
        url = "https://proverkacheka.com/api/v1/check/get"
        
        data = {'token': self.api, "qrraw": self.qr_string}

        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()

            json_data = response.json()
            items = json_data.get("data", {}).get("json", {}).get("items", [])

            if not isinstance(items, list):
                st.error("Неожиданный формат ответа от ФНС.")
                return []
            
            item_strings = []
            for item in items:
                name = item.get("name")
                name = re.sub(r"\(.*?\)", "", name)
                name = re.sub(r"\s+", " ", name).strip()

                price = item.get("price", 0) / 100
                qty = item.get("quantity")
                item_string = f"{name} — {price:.2f} руб. x {qty} шт."
                item_strings.append(item_string)

            return item_strings

        except requests.exceptions.Timeout:
            st.error("Сервис ФНС не ответил вовремя. Попробуйте ещё раз.")
            return []
        except requests.exceptions.HTTPError as e:
            st.error(f"Ошибка сервиса ФНС: {e.response.status_code}") # type: ignore
            return []
        except requests.RequestException as e:
            st.error(f"Ошибка сети: {e}")
            return []
        except (KeyError, ValueError) as e:
            st.error(f"Ошибка разбора ответа: {e}")
            return []
