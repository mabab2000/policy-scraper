from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import uuid

try:
	from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
	async_playwright = None

from starlette.responses import JSONResponse

app = FastAPI()
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class ScrapeRequest(BaseModel):
	url: str
	filename: str | None = None
	wait_for: str | None = None
	timeout: int | None = 30000


@app.post("/scrape")
async def scrape(body: ScrapeRequest):
	if async_playwright is None:
		raise HTTPException(status_code=500, detail="Playwright is not installed. See README to install dependencies.")

	url = body.url
	filename = body.filename or f"{uuid.uuid4().hex}.pdf"
	pdf_path = os.path.join(OUTPUT_DIR, filename)

	try:
		async with async_playwright() as p:
			browser = await p.chromium.launch()
			context = await browser.new_context()
			page = await context.new_page()
			await page.goto(url, timeout=body.timeout, wait_until="networkidle")
			if body.wait_for:
				try:
					await page.wait_for_selector(body.wait_for, timeout=body.timeout)
				except PlaywrightTimeoutError:
					pass
			await page.pdf(path=pdf_path, format="A4", print_background=True)
			from fastapi import FastAPI, HTTPException
			from pydantic import BaseModel
			from fastapi import FastAPI, HTTPException
			from pydantic import BaseModel
			from typing import List
			from fastapi import FastAPI, HTTPException
			from pydantic import BaseModel
			from typing import List
			import os

			try:
				from playwright.async_api import async_playwright
			except Exception:
				async_playwright = None

			from starlette.responses import JSONResponse


			app = FastAPI()
			OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output_pdfs")
			os.makedirs(OUTPUT_DIR, exist_ok=True)


			class ScrapeRequest(BaseModel):
				urls: List[str]
				project_id: str


			@app.post("/scrape")
			async def scrape(body: ScrapeRequest):
				if async_playwright is None:
					raise HTTPException(status_code=500, detail="Playwright is not installed. See README to install dependencies.")
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import os

try:
	from playwright.async_api import async_playwright
except Exception:
	async_playwright = None

from starlette.responses import JSONResponse


app = FastAPI()
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class ScrapeRequest(BaseModel):
	urls: List[str]
	project_id: str


@app.post("/scrape")
async def scrape(body: ScrapeRequest):
	if async_playwright is None:
		raise HTTPException(status_code=500, detail="Playwright is not installed. See README to install dependencies.")
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import os

try:
	from playwright.async_api import async_playwright
except Exception:
	async_playwright = None

from starlette.responses import JSONResponse


app = FastAPI()
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class ScrapeRequest(BaseModel):
	urls: List[str]
	project_id: str


@app.post("/scrape")
async def scrape(body: ScrapeRequest):
	if async_playwright is None:
		raise HTTPException(status_code=500, detail="Playwright is not installed. See README to install dependencies.")

	project_dir = os.path.join(OUTPUT_DIR, body.project_id)
	os.makedirs(project_dir, exist_ok=True)
	results = []

	try:
		async with async_playwright() as p:
			browser = await p.chromium.launch()
			context = await browser.new_context()

			for idx, url in enumerate(body.urls, start=1):
				page = await context.new_page()
				pdf_name = f"{body.project_id}_{idx}.pdf"
				pdf_path = os.path.join(project_dir, pdf_name)
				try:
					await page.goto(url, timeout=30000, wait_until="networkidle")
					await page.pdf(path=pdf_path, format="A4", print_background=True)
					results.append({"url": url, "pdf": pdf_path})
				except Exception as e:
					results.append({"url": url, "error": str(e)})
				finally:
					await page.close()

			await browser.close()
	except Exception as exc:
		raise HTTPException(status_code=500, detail=str(exc))

	return JSONResponse({"results": results})


if __name__ == "__main__":
	import uvicorn

	uvicorn.run("main:app", host="0.0.0.0", port=8000)
