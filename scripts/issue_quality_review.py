import os

import requests

GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
MODELS_API = "https://models.github.ai/inference/chat/completions"
MODEL = os.environ.get("REVIEW_MODEL", "openai/gpt-4o-mini")
MARKER = "<!-- issue-quality-review-bot -->"

REPO = os.environ["GITHUB_REPOSITORY"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]
TOKEN = os.environ["GITHUB_TOKEN"]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def get_json(url, **kwargs):
    resp = requests.get(url, headers=HEADERS, **kwargs)
    resp.raise_for_status()
    return resp.json()


def fetch_issue():
    return get_json(f"{GITHUB_API}/repos/{REPO}/issues/{ISSUE_NUMBER}")


def fetch_comments():
    comments, page = [], 1
    while True:
        batch = get_json(
            f"{GITHUB_API}/repos/{REPO}/issues/{ISSUE_NUMBER}/comments",
            params={"per_page": 100, "page": page},
        )
        comments.extend(batch)
        if len(batch) < 100:
            return comments
        page += 1


def build_prompt(issue, comments):
    thread = "\n\n".join(
        f"{c['user']['login']}: {c['body']}"
        for c in comments
        if MARKER not in (c.get("body") or "") and c["body"].strip() != "/review-issue"
    )
    return f"""You are reviewing a GitHub issue for developer-readiness.

Title: {issue["title"]}

Body:
{issue["body"] or "(empty)"}

Discussion so far:
{thread or "(no comments yet)"}

Write a review with exactly these four sections, each with the given emoji heading:

📊 Scope
📝 Context & Guidance
⚡ Complexity
🎯 Overall Issue Quality Verdict

Keep each section to 2-4 short bullet points, plus a one-line verdict at the \
end of the last section stating whether this is ready for a developer to pick up."""


def call_model(prompt):
    resp = requests.post(
        MODELS_API,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def find_existing_comment(comments):
    for c in comments:
        if MARKER in (c.get("body") or ""):
            return c["id"]
    return None


def upsert_comment(body, existing_id):
    payload = {"body": f"{MARKER}\n{body}"}
    if existing_id:
        url = f"{GITHUB_API}/repos/{REPO}/issues/comments/{existing_id}"
        requests.patch(url, headers=HEADERS, json=payload).raise_for_status()
    else:
        url = f"{GITHUB_API}/repos/{REPO}/issues/{ISSUE_NUMBER}/comments"
        requests.post(url, headers=HEADERS, json=payload).raise_for_status()


def main():
    issue = fetch_issue()
    comments = fetch_comments()
    review = call_model(build_prompt(issue, comments))
    upsert_comment(review, find_existing_comment(comments))


if __name__ == "__main__":
    main()
