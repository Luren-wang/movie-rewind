import json
import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MOVIES_CSV = DATA_DIR / "movies.csv"
FALLBACK_TRENDING = DATA_DIR / "fallback_trending.json"
FALLBACK_NOW_SHOWING = DATA_DIR / "fallback_now_showing.json"
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

app = Flask(__name__)


def tmdb_get(path, params=None):
    if not TMDB_API_KEY:
        return None
    query = {"api_key": TMDB_API_KEY, "language": "zh-TW"}
    if params:
        query.update(params)
    try:
        response = requests.get(f"{TMDB_BASE_URL}{path}", params=query, timeout=8)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


@lru_cache(maxsize=1)
def load_movies():
    df = pd.read_csv(MOVIES_CSV)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").fillna(0).astype(int)
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0.0)
    df["vote_count"] = pd.to_numeric(df["vote_count"], errors="coerce").fillna(0).astype(int)
    df["popularity"] = pd.to_numeric(df["popularity"], errors="coerce").fillna(0.0)
    return df


def split_values(value):
    if pd.isna(value) or not str(value).strip():
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def movie_record(row):
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "year": int(row["year"]),
        "genres": split_values(row["genres"]),
        "rating": float(row["rating"]),
        "vote_count": int(row["vote_count"]),
        "popularity": float(row["popularity"]),
        "keywords": split_values(row["keywords"]),
        "overview": row["overview"],
        "poster_url": row["poster_url"],
        "status": row["status"],
    }


def local_movie_by_id(movie_id):
    df = load_movies()
    match = df[df["id"].astype(str) == str(movie_id)]
    if match.empty:
        return None
    return movie_record(match.iloc[0])


def local_search(query):
    df = load_movies()
    normalized = query.strip().lower()
    if not normalized:
        return []
    matches = df[df["title"].str.lower().str.contains(normalized, na=False)]
    return [movie_record(row) for _, row in matches.head(12).iterrows()]


def tmdb_movie_summary(item):
    year = 0
    if item.get("release_date"):
        year = int(item["release_date"].split("-")[0])
    poster_url = ""
    if item.get("poster_path"):
        poster_url = f"{TMDB_IMAGE_BASE}{item['poster_path']}"
    return {
        "id": item.get("id"),
        "title": item.get("title") or item.get("name") or "Untitled",
        "year": year,
        "genres": [],
        "rating": float(item.get("vote_average") or 0),
        "vote_count": int(item.get("vote_count") or 0),
        "popularity": float(item.get("popularity") or 0),
        "keywords": [],
        "overview": item.get("overview") or "",
        "poster_url": poster_url,
        "status": "api",
    }


def get_movie(movie_id):
    local = local_movie_by_id(movie_id)
    if local:
        return local

    detail = tmdb_get(
        f"/movie/{movie_id}",
        {"append_to_response": "keywords", "language": "zh-TW"},
    )
    if not detail:
        return None

    year = 0
    if detail.get("release_date"):
        year = int(detail["release_date"].split("-")[0])
    poster_url = f"{TMDB_IMAGE_BASE}{detail['poster_path']}" if detail.get("poster_path") else ""
    return {
        "id": detail.get("id"),
        "title": detail.get("title", "Untitled"),
        "year": year,
        "genres": [genre["name"] for genre in detail.get("genres", [])],
        "rating": float(detail.get("vote_average") or 0),
        "vote_count": int(detail.get("vote_count") or 0),
        "popularity": float(detail.get("popularity") or 0),
        "keywords": [item["name"] for item in detail.get("keywords", {}).get("keywords", [])],
        "overview": detail.get("overview") or "",
        "poster_url": poster_url,
        "status": "api",
    }


def absolute_atmovies_url(path):
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return f"https://www.atmovies.com.tw{path}"


@lru_cache(maxsize=64)
def get_showing_detail(code):
    try:
        response = requests.get(
            f"https://www.atmovies.com.tw/movie/{code}/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    title_node = soup.select_one("div.filmTitle")
    block = soup.select_one("#filmTagBlock")
    poster_node = soup.select_one("#filmTagBlock img")

    title = title_node.get_text(" ", strip=True) if title_node else code
    block_text = " ".join(block.get_text(" ", strip=True).split()) if block else ""
    overview = block_text.split("片長：", 1)[0].strip() if "片長：" in block_text else block_text

    runtime_match = re.search(r"片長：(\d+)分", block_text)
    date_match = re.search(r"上映日期：(\d{4}/\d{2}/\d{2})", block_text)
    theaters_match = re.search(r"廳數\s*\((\d+)\)", block_text)

    return {
        "code": code,
        "title": title,
        "overview": overview,
        "runtime": int(runtime_match.group(1)) if runtime_match else 0,
        "date": date_match.group(1) if date_match else "",
        "theaters": int(theaters_match.group(1)) if theaters_match else 0,
        "poster_url": absolute_atmovies_url(poster_node.get("src")) if poster_node else "",
    }


def scrape_taiwan_now_showing():
    try:
        response = requests.get(
            "https://www.atmovies.com.tw/movie/now/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException:
        return [], "備援資料"

    soup = BeautifulSoup(response.text, "html.parser")
    movies = []
    pattern = re.compile(r"(.+?)\s+(\d{4}/\d{1,2}/\d{1,2})\s+\((\d+)分\)\s+\((\d+)廳\)")
    for item in soup.select("li"):
        text = " ".join(item.get_text(" ", strip=True).split())
        match = pattern.search(text)
        if not match:
            continue
        link = item.find("a", href=re.compile(r"^/movie/[^/]+/"))
        if not link:
            continue
        code = link["href"].strip("/").split("/")[-1]
        detail = get_showing_detail(code) or {}
        movies.append(
            {
                "code": code,
                "title": match.group(1).strip(),
                "date": match.group(2),
                "runtime": int(match.group(3)),
                "theaters": int(match.group(4)),
                "poster_url": detail.get("poster_url", ""),
                "overview": detail.get("overview", ""),
            }
        )
        if len(movies) >= 8:
            break

    if movies:
        return movies, "開眼電影網本期首輪上映"
    return [], "備援資料"


def fallback_now_showing():
    with FALLBACK_NOW_SHOWING.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_now_showing():
    movies, source = scrape_taiwan_now_showing()
    if movies:
        return movies, source
    return fallback_now_showing(), source


def fallback_trending():
    with FALLBACK_TRENDING.open(encoding="utf-8") as f:
        items = json.load(f)
    return [get_movie(item["id"]) for item in items if get_movie(item["id"])]


def get_top_rated_movies(limit=8):
    df = load_movies().copy()
    ranked = df.sort_values(["rating", "vote_count"], ascending=[False, False])
    return [movie_record(row) for _, row in ranked.head(limit).iterrows()]


def search_movies(query):
    tmdb_data = tmdb_get("/search/movie", {"query": query, "include_adult": "false"})
    if tmdb_data and tmdb_data.get("results"):
        return [tmdb_movie_summary(item) for item in tmdb_data["results"][:12]]
    return local_search(query)


def set_ratio(a_values, b_values):
    a = {value.lower() for value in a_values}
    b = {value.lower() for value in b_values}
    if not a or not b:
        return 0.0, set()
    overlap = a & b
    return len(overlap) / max(len(a), 1), overlap


def recommendation_reason(candidate, genre_overlap, keyword_overlap):
    reasons = []
    if genre_overlap:
        reasons.append(f"類型相近：{', '.join(sorted(genre_overlap))}")
    if keyword_overlap:
        reasons.append(f"主題關鍵字相似：{', '.join(sorted(keyword_overlap))}")
    if candidate["rating"] >= 8:
        reasons.append(f"評分高達 {candidate['rating']:.1f}")
    if candidate["year"] <= 2000:
        reasons.append("上映超過 20 年，符合補經典老片的目標")
    if not reasons:
        reasons.append("整體評分與歷史人氣表現穩定")
    return "；".join(reasons)


def score_old_movie_candidates(source_movie):
    df = load_movies()
    old_df = df[
        (df["status"] == "old")
        & (df["year"] <= 2015)
        & (df["rating"] >= 7.0)
        & (df["vote_count"] >= 300)
    ].copy()

    source_genres = source_movie.get("genres", [])
    source_keywords = source_movie.get("keywords", [])
    scored = []

    for _, row in old_df.iterrows():
        candidate = movie_record(row)
        if str(candidate["id"]) == str(source_movie["id"]):
            continue

        genre_score, genre_overlap = set_ratio(source_genres, candidate["genres"])
        keyword_score, keyword_overlap = set_ratio(source_keywords, candidate["keywords"])
        rating_score = min(candidate["rating"] / 10, 1.0)
        age_score = min(max((2026 - candidate["year"]) / 50, 0), 1.0)
        popularity_score = min(candidate["vote_count"] / 20000, 1.0)

        total = (
            genre_score * 40
            + keyword_score * 30
            + rating_score * 18
            + age_score * 8
            + popularity_score * 4
        )

        candidate["score"] = round(total, 1)
        candidate["reason"] = recommendation_reason(candidate, genre_overlap, keyword_overlap)
        scored.append(candidate)

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored


def recommend_old_movies(source_movie, limit=5):
    return score_old_movie_candidates(source_movie)[:limit]


def analyze_recommendations(source_movie, candidates):
    source_genres = {genre.lower() for genre in source_movie.get("genres", [])}
    same_genre_year_counts = {}
    same_year_genre_counts = {}
    source_year = int(source_movie.get("year") or 0)

    for movie in candidates:
        movie_genres = {genre.lower() for genre in movie["genres"]}
        if source_genres & movie_genres:
            decade = movie["year"] // 10 * 10
            year_label = f"{decade}年代"
            same_genre_year_counts[year_label] = same_genre_year_counts.get(year_label, 0) + 1

        if source_year:
            same_decade = movie["year"] // 10 == source_year // 10
            close_year = abs(movie["year"] - source_year) <= 5
            if same_decade or close_year:
                for genre in movie["genres"]:
                    same_year_genre_counts[genre] = same_year_genre_counts.get(genre, 0) + 1

    if not same_year_genre_counts and candidates:
        year_counts = {}
        for movie in candidates:
            year_counts[movie["year"]] = year_counts.get(movie["year"], 0) + 1
        target_year = sorted(year_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        for movie in candidates:
            if movie["year"] == target_year:
                for genre in movie["genres"]:
                    same_year_genre_counts[genre] = same_year_genre_counts.get(genre, 0) + 1

    same_genre_year_counts = dict(
        sorted(same_genre_year_counts.items(), key=lambda item: int(item[0].replace("年代", "")))
    )
    same_year_genre_counts = dict(
        sorted(same_year_genre_counts.items(), key=lambda item: item[1], reverse=True)
    )

    return {
        "sameGenreYears": {
            "labels": list(same_genre_year_counts.keys()),
            "values": list(same_genre_year_counts.values()),
            "label": "同類型電影數量",
        },
        "sameYearGenres": {
            "labels": list(same_year_genre_counts.keys()),
            "values": list(same_year_genre_counts.values()),
            "label": "同年代類型數量",
        },
    }


@app.route("/")
def index():
    now_showing, now_showing_source = get_now_showing()
    return render_template(
        "index.html",
        top_rated=get_top_rated_movies(),
        now_showing=now_showing,
        now_showing_source=now_showing_source,
    )


@app.route("/search")
def search_page():
    query = request.args.get("query", "").strip()
    results = search_movies(query) if query else []
    return render_template("search.html", query=query, results=results)


@app.route("/movie/<int:movie_id>")
def movie_page(movie_id):
    movie = get_movie(movie_id)
    if not movie:
        return render_template("not_found.html"), 404
    return render_template("movie.html", movie=movie)


@app.route("/recommend/<int:movie_id>")
def recommend_page(movie_id):
    movie = get_movie(movie_id)
    if not movie:
        return render_template("not_found.html"), 404
    candidates = score_old_movie_candidates(movie)
    recommendations = candidates[:5]
    analysis = analyze_recommendations(movie, candidates)
    return render_template(
        "recommend.html",
        movie=movie,
        recommendations=recommendations,
        analysis=analysis,
    )


@app.route("/showing/<code>")
def showing_page(code):
    movie = get_showing_detail(code)
    if not movie:
        for item in fallback_now_showing():
            if item.get("code") == code:
                movie = item
                break
    if not movie:
        return render_template("not_found.html"), 404
    return render_template("showing.html", movie=movie)


@app.route("/api/trending")
def api_trending():
    return jsonify(get_top_rated_movies())


@app.route("/api/now-showing")
def api_now_showing():
    movies, source = get_now_showing()
    return jsonify({"source": source, "movies": movies})


@app.route("/api/search")
def api_search():
    query = request.args.get("query", "").strip()
    return jsonify(search_movies(query) if query else [])


@app.route("/api/movie/<int:movie_id>")
def api_movie(movie_id):
    movie = get_movie(movie_id)
    if not movie:
        return jsonify({"error": "movie not found"}), 404
    return jsonify(movie)


@app.route("/api/recommend/<int:movie_id>")
def api_recommend(movie_id):
    movie = get_movie(movie_id)
    if not movie:
        return jsonify({"error": "movie not found"}), 404
    candidates = score_old_movie_candidates(movie)
    recommendations = candidates[:5]
    return jsonify(
        {
            "source": movie,
            "recommendations": recommendations,
            "analysis": analyze_recommendations(movie, candidates),
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
