# USAA Fraud Project

## Team:
 - Val Nikolov
 - Calvin Zheng
 - Peyton Sharpe
 - Jelani Latimore

**DTSC 3602 | UNC Charlotte**
---

## Project Summary
This GitHub repository contains the full code, including scrapers, readers, and analysis, regarding the **USAA Fraud Project** as part of a final project in **Predictive Analytics at UNC Charlotte**.

This includes the processes of scraping articles from the cybersecurity website, **"BleepingComputer"**, following that up with analysis, modeling, and finally deployment using **Streamlit**. 
---

## 🛠️ Pipeline

The process is split into a few stages.

#### Stage 1 - Scraping
 - Scraper built using BeautifulSoup4, requests
 - From **BleepingComputer**, articles are scraped and added into a raw file

#### Stage 2 - Parsing
 - Following the scraper, we use json, sentence_transformer, urljoin for transformation and parsing
 - Take all the raw data, put it into a json file full of fraud related articles
 - Organize data into separate csv files with fraud only articles, all articles, and so on.

#### Stage 3 - Upload
 - Implementation of **Supabase** and **Streamlit**
 - Upload the fraud articles dataset to **Supabase**
 - Use **Streamlit** to deploy app and visualizations.

---

## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/DTSC-3602.git
cd DTSC-3602
```

### 2. Create Environment
Using **uv** (preferred) or Conda:
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the project root with:
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
```

### 4. Run the Streamlit App
```bash
uv run streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`.

---

## Modeling Description
Using embedding models, we were able to parse and collect articles of different types, as well as find the different fraud types being discussed in cybersecurity, giving us hints as to how to spot and deal with them.
 - Here we used the **sentence_transformer** for the embeddings
 - Specific functions to summarize articles 
 - Follow up with visualizations for the summaries and fraud keywords

## 🚀 Tech Stack
 - **Python 3.12**
 - **Streamlit** - interactive dashboard application
 - **Supabase** - storage and vector similarity
 - **sentence_transformer** - embedding models
 - **Pandas**, **Matplotlib** - visualizations, modeling, analysis
 - **BeautifulSoup4**, **requests**, **urljoin**, **json** - Scraping, parsing, transformation

