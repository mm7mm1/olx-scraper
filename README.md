# Асинхронний скрапер нерухомості OLX.ua
Даний проєкт є реалізуванням парсингу даних з відкритих джерел.

## Опис рішення
Реалізовано **асинхронне рішення** на базі бібліотеки **Playwright**. Це дозволяє значно прискорити збір даних завдяки паралельній обробці сторінок.

### Технологічний стек:
- **Python 3.14** (використано для розробки)
- **Playwright (Async)** — для взаємодії з динамічним контентом та виконання JavaScript на сторінці.
- **Pandas** — для структурування та первинної обробки даних.
- **Google Sheets API (gspread)** — для автоматичного експорту результатів у хмару.
- **python-dotenv** — для безпечного керування секретами.

## Виконані вимоги
- [x] **Асинхронність**: Використано `asyncio.gather` та семафори для контролю навантаження.
- [x] **JS Injection**: Парсинг основних параметрів виконано через `page.evaluate()`, що підвищує швидкість роботи.
- [x] **Безпека**: Всі чутливі дані (credentials, .env) винесені в ігнорування Git.
- [x] **Структура**: Дані очищуються від зайвих символів та конвертуються у відповідні типи (int, float).

## Результати
- **Посилання на Google Sheet**: [Google Sheets](https://docs.google.com/spreadsheets/d/1JhhJJiNZH7uMk3_BsNMfgja1HvTiWapxGlSepKkYOcw/edit?usp=sharing)
- **Дані, що парсяться**: Ціна, поверх, поверховість, населений пункт, область, площа та URL оголошення.

## Налаштування та запуск

### 1. Підготовка Google Cloud (API)
Для роботи з таблицями необхідно отримати доступ:
1. Відкрити [Google Cloud Console](https://console.cloud.google.com/).
2. Створити новий проєкт.
3. У розділі **APIs & Services** увімкнути `Google Sheets API` та `Google Drive API`.
4. Перейти в **IAM & Admin** → **Service Accounts** → Створи сервісний акаунт.
5. Відкрити створений акаунт → **Keys** → **Add Key** → **Create new key (JSON)**.
6. Зберегти завантажений файл як `credentials.json` у кореневу папку проєкту.
7. **Важливо**: Відкрити свій Google Sheet, натисни **Поділитися** та додати email зі свого JSON-файлу (поле `client_email`) з правами **Редактор**.

### 2. Налаштування оточення
1. Створити файл `.env` у папці проєкту.
2. Додати наступні змінні:
    ```bash
   GOOGLE_CREDENTIALS_PATH=/шлях/до/твого/credentials.json
   GOOGLE_SHEET_ID=ідентифікатор_твоєї_таблиці
3. Встановлення залежностей
    ```bash
    pip install -r requirements.txt
    playwright install chromium
4. Запуск
    ```bash
    python main.py


## License
This project is licensed under the MIT License. You are free to use, modify, and share this project with proper attribution.


## About me 
Hey, my name is Anastasiia, I am a Data Engineer wanting to achieve high results.
<br>
I'm open to feedback and would love to discuss the architectural choices I made in this project! <br>
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/anastasiia-kukhar-mm7mm1/)