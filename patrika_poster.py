import json
import os
import time
import feedparser
from google import genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import requests

# Purani API keys aur Token same chalenge
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TOKEN_JSON_DATA = os.environ.get("TOKEN_JSON")

client = genai.Client(api_key=GEMINI_API_KEY)

# Patrika Rajasthan News RSS Feed URL
PATRIKA_RSS_URL = "https://www.patrika.com/rajasthan-news"
SCOPES = ["https://www.googleapis.com/auth/blogger"]


def get_blogger_service():
  creds = None
  if TOKEN_JSON_DATA:
    token_info = json.loads(TOKEN_JSON_DATA)
    creds = Credentials.from_authorized_user_info(token_info, SCOPES)

  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      raise Exception("Blogger authentication fail ho gaya.")

  return build("blogger", "v3", credentials=creds)


def fetch_patrika_news():
  headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

  # Retry Mechanism (Max 3 Tries)
  for attempt in range(1, 4):
    try:
      print(f"Patrika Feed fetch ho raha hai... (Attempt {attempt})")
      response = requests.get(
          PATRIKA_RSS_URL, headers=headers, allow_redirects=True, timeout=15
      )
      response.raise_for_status()
      feed = feedparser.parse(response.content)
      if feed.entries:
        return feed.entries
    except Exception as e:
      print(f"Attempt {attempt} failed: {e}")
      time.sleep(10)

  return []


def process_news_with_gemini(entry):
  hindi_title = entry.title
  hindi_summary = entry.get("summary", entry.get("description", ""))

  print(f"Processing News: {hindi_title}")

  prompt = f"""
    You are an expert English journalist and SEO editor.
    Translate and rewrite the following Hindi local news from Rajasthan Patrika into English.

    STRICT RULES:
    1. If the news is strictly about International affairs or foreign countries (outside India), respond ONLY with "SKIP_NEWS".
    2. Focus only on Local/State/National news relevant to Rajasthan and India.
    3. Write a catchy SEO English title.
    4. Provide HTML body content (<p>, <h2>).
    5. Add 5-8 trending English hashtags at the end (e.g. #RajasthanNews #IndiaUpdates).
    6. Provide 3-5 category labels separated by commas.

    Hindi Title: {hindi_title}
    Hindi Summary: {hindi_summary}

    Output format strictly as:
    TITLE: [SEO English Title]
    LABELS: [Label1, Label2, Label3]
    CONTENT: [HTML Content with Hashtags at bottom]
    """

  # Retry Gemini API call on server busy
  ai_output = ""
  for attempt in range(1, 4):
    try:
      response = client.models.generate_content(
          model="gemini-3.8-flash", contents=prompt
      )
      ai_output = response.text
      break
    except Exception as e:
      print(f"Gemini error attempt {attempt}: {e}")
      time.sleep(10)

  if "SKIP_NEWS" in ai_output:
    print("International news detected, skipping post.")
    return None, None, None

  try:
    title_part = ai_output.split("LABELS:")[0].replace("TITLE:", "").strip()
    remainder = ai_output.split("LABELS:")[1]
    labels_part = remainder.split("CONTENT:")[0].strip()
    content_part = remainder.split("CONTENT:")[1].strip()
    labels_list = [l.strip() for l in labels_part.split(",") if l.strip()]
  except Exception:
    title_part = f"Rajasthan News: {hindi_title}"
    labels_list = ["Rajasthan News", "Local News"]
    content_part = f"<p>{ai_output}</p>"

  return title_part, labels_list, content_part


def post_to_blogger(title, labels, content):
  service = get_blogger_service()
  # Aapke same Blogger account ka pehla blog select karega
  blogs = service.blogs().listByUser(userId="self").execute()
  blog_id = blogs["items"][0]["id"]

  body = {"title": title, "labels": labels, "content": content}

  post = service.posts().insert(blogId=blog_id, body=body).execute()
  print(f"Post publish ho gayi: {post['url']}")


if __name__ == "__main__":
  entries = fetch_patrika_news()
  if entries:
    # Latest news process karke post karein
    for entry in entries[:3]:
      title, labels, content = process_news_with_gemini(entry)
      if title and content:
        post_to_blogger(title, labels, content)
        time.sleep(5)
  else:
    print("Koi nayi news nahi mili.")
