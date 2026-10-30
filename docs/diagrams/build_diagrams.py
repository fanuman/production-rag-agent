"""Draws the README diagrams as SVG files. No dependencies: run `python docs/diagrams/build_diagrams.py`.

Edit the text below, run it again, and commit the changed SVGs in docs/images/.
Every picture has a white background so it reads the same on GitHub's light and dark themes.
Colours: blue = calls the OpenAI API, green = plain code, amber = decides or acts (cache check,
scope check, tools), violet = a store (Redis, Chroma), grey = start, end or outside the app.
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "images"

FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
INK, SOFT = "#111827", "#4b5563"

KINDS = {  # fill, stroke
    "llm": ("#dbeafe", "#2563eb"),
    "code": ("#dcfce7", "#16a34a"),
    "decide": ("#fef3c7", "#d97706"),
    "store": ("#ede9fe", "#7c3aed"),
    "end": ("#f3f4f6", "#6b7280"),
    "plain": ("#ffffff", "#9ca3af"),
}
ARROW_COLORS = {"ink": "#374151", "amber": "#d97706", "red": "#dc2626"}
LINE_H = {"t": 21, "d": 17, "m": 15}
CHAR_W = {"t": 8.9, "d": 7.0, "m": 6.4}   # rough text widths, used only to warn about overflow


class Svg:
    def __init__(self, w, h, title, desc):
        self.w, self.h, self.parts = w, h, []
        self.title, self.desc = title, desc

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=13, weight="normal", fill=INK, anchor="start", family=FONT, italic=False, halo=False):
        extra = ' stroke="#ffffff" stroke-width="5" stroke-linejoin="round" paint-order="stroke"' if halo else ""
        style = ' font-style="italic"' if italic else ""
        self.add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{fill}" text-anchor="{anchor}"{style}{extra}>{escape(s)}</text>')

    def rect(self, x, y, w, h, kind="plain", r=10, dashed=False, sw=1.6, fill=None):
        f, st = KINDS[kind]
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill or f}" stroke="{st}" stroke-width="{sw}"{dash}/>')

    def lines_block(self, cx, cy, lines):
        """lines = [(text, 't'|'d'|'m'), ...] centred vertically on cy."""
        total = sum(LINE_H[k] for _, k in lines)
        y = cy - total / 2
        for s, k in lines:
            y += LINE_H[k]
            base = y - (5 if k == "t" else 4)
            if k == "t":
                self.text(cx, base, s, 15, "bold", INK, "middle")
            elif k == "d":
                self.text(cx, base, s, 12.5, "normal", SOFT, "middle")
            else:
                self.text(cx, base, s, 10.5, "normal", "#6b7280", "middle", MONO)

    def node(self, cx, cy, w, h, kind, lines, dashed=False):
        for s, k in lines:   # warn if a line is probably wider than its box
            if len(s) * CHAR_W[k] > w - 14:
                print(f"  warning: '{s}' may overflow its {w}px box")
        self.rect(cx - w / 2, cy - h / 2, w, h, kind, dashed=dashed)
        self.lines_block(cx, cy, lines)

    def frame(self, x, y, w, h, kind, label):
        f, st = KINDS[kind]
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{f}" fill-opacity="0.35" '
                 f'stroke="{st}" stroke-width="1.6" stroke-dasharray="7 5"/>')
        self.text(x + 16, y + 26, label, 13.5, "bold", SOFT)

    def arrow(self, pts, color="ink", dashed=False, width=2.0):
        d = " ".join(("M" if i == 0 else "L") + f"{x},{y}" for i, (x, y) in enumerate(pts))
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.add(f'<path d="{d}" fill="none" stroke="{ARROW_COLORS[color]}" stroke-width="{width}" '
                 f'stroke-linejoin="round" marker-end="url(#a-{color})"{dash}/>')

    def label(self, x, y, s, anchor="middle", color=SOFT, size=12):
        self.text(x, y, s, size, "normal", color, anchor, halo=True)

    def render(self):
        markers = "".join(
            f'<marker id="a-{n}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for n, c in ARROW_COLORS.items())
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
                f'role="img" aria-labelledby="t d"><title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>'
                f'<defs>{markers}</defs><rect width="{self.w}" height="{self.h}" fill="#ffffff"/>' + "".join(self.parts) + "</svg>")

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_text(self.render(), encoding="utf-8")
        print("wrote", OUT / name)


def header(s, title, subtitle):
    s.text(30, 42, title, 22, "bold")
    s.text(30, 68, subtitle, 15, "normal", SOFT)


def legend(s, y, items):
    x = 30
    for kind, label in items:
        s.rect(x, y, 26, 18, kind, r=4, sw=1.4)
        s.text(x + 34, y + 14, label, 12.5, "normal", SOFT)
        x += 34 + len(label) * 6.6 + 26


# ---------------------------------------------------------------- 1. the containers
def containers():
    s = Svg(1280, 640, "The three containers",
            "A browser talks to the app container (FastAPI). The app uses a Redis container for the semantic cache "
            "and rate-limit counters, a Chroma container for the document index, the OpenAI API for the model, and "
            "AWS Secrets Manager for the API key when deployed. The same three containers run under Docker Compose, "
            "ECS/Fargate and Kubernetes.")
    header(s, "The system: three containers",
           "app, chroma and redis. Defined once for Compose, once for ECS/Fargate (Terraform), once for Kubernetes.")

    s.node(105, 215, 150, 96, "end", [("Browser", "t"), ("web UI at /", "d"), ("or curl", "d")])

    s.frame(270, 130, 420, 282, "code", "app container: FastAPI + uvicorn")
    s.node(480, 215, 370, 58, "code", [("API routes + rate limit", "t"), ("/ask/stream  /ask  /cost  /health", "m")])
    s.node(480, 290, 370, 58, "code", [("RAGPipeline", "t"), ("cache, retrieve, agent loop, sources", "d")])
    s.node(480, 365, 370, 58, "code", [("Web UI files", "t"), ("frontend/ served at / (same origin)", "d")])

    s.node(900, 205, 220, 96, "store", [("redis container", "t"), ("semantic cache", "d"), ("rate-limit counters", "d")])
    s.node(900, 345, 220, 96, "store", [("chroma container", "t"), ("index of data/*.txt", "d"), ("port 8001", "m")])
    s.node(1150, 205, 190, 96, "llm", [("OpenAI API", "t"), ("gpt-4o-mini", "d"), ("embeddings", "d")])
    s.node(1150, 345, 190, 96, "end", [("AWS Secrets Manager", "t"), ("OpenAI key (ECS)", "d"), ("via IAM task role", "d")])

    s.arrow([(180, 215), (295, 215)])
    s.label(232, 205, "HTTP + SSE")
    s.arrow([(665, 290), (740, 290), (740, 205), (790, 205)])
    s.arrow([(740, 290), (740, 345), (790, 345)])
    s.arrow([(480, 130), (480, 98), (1150, 98), (1150, 157)])
    s.label(815, 90, "chat, embeddings, streaming")
    s.arrow([(480, 412), (480, 462), (1150, 462), (1150, 393)], dashed=True)
    s.label(815, 454, "key fetched at startup; .env fallback for local development")

    s.text(30, 508, "The same three containers in three environments", 15, "bold")
    s.node(215, 566, 370, 66, "plain", [("Docker Compose (local)", "t"), ("src/ data/ frontend/ logs/ mounted, --reload", "d")])
    s.node(640, 566, 400, 66, "plain", [("ECS/Fargate (Terraform)", "t"), ("one task; containers share localhost", "d")])
    s.node(1065, 566, 370, 66, "plain", [("Kubernetes (Minikube)", "t"), ("Deployments + Services, DNS names", "d")])
    legend(s, 612, [("llm", "calls the OpenAI API"), ("code", "plain code"), ("store", "a store"), ("end", "outside the app")])
    s.save("containers.svg")


# ---------------------------------------------------------------- 2. one question
def question_path():
    s = Svg(1280, 690, "The path of one question",
            "The question is embedded and looked up in the semantic cache. On a miss, the top five chunks are retrieved "
            "from Chroma and checked for relevance. In scope, the agent loop lets the model call tools until it writes the "
            "answer, streaming tokens to the browser. The SOURCES line is hidden and turned into source chips, the answer "
            "is cached if no tool was used, and a done event ends the stream.")
    header(s, "What happens to one question in /ask/stream",
           "Row 1 decides whether to answer at all. Row 2 writes the answer and streams it.")

    y1 = 225
    s.node(95, y1, 140, 84, "end", [("Question", "t"), ("from the UI", "d")])
    s.node(275, y1, 150, 84, "llm", [("embed", "t"), ("question to vector", "d"), ("OpenAI", "m")])
    s.node(470, y1, 170, 84, "decide", [("cache hit?", "t"), ("close to an old one?", "d"), ("Redis", "m")])
    s.node(675, y1, 160, 84, "store", [("retrieve", "t"), ("top 5 chunks", "d"), ("Chroma", "m")])
    s.node(880, y1, 170, 84, "decide", [("in scope?", "t"), ("closest chunk < 0.68", "d"), ("distance", "m")])
    s.node(1115, y1, 210, 84, "end", [("fallback message", "t"), ("no model call", "d"), ("done: fallback", "m")])
    s.node(470, 118, 270, 54, "end", [("saved answer, sent at once", "t"), ("done: cached", "m")])

    s.arrow([(165, y1), (200, y1)])
    s.arrow([(350, y1), (385, y1)])
    s.arrow([(555, y1), (595, y1)], color="ink")
    s.label(575, y1 - 12, "miss")
    s.arrow([(470, y1 - 42), (470, 145)], color="amber")
    s.label(492, 168, "hit", anchor="start")
    s.arrow([(755, y1), (795, y1)])
    s.arrow([(965, y1), (1010, y1)], color="red")
    s.label(988, y1 - 12, "no")
    s.arrow([(880, y1 + 42), (880, 335)], color="ink")
    s.label(902, 310, "yes", anchor="start")

    # row 2: agent loop (right) then leftwards
    s.frame(560, 335, 700, 215, "llm", "agent loop: every model call is streamed")
    s.node(735, 455, 200, 84, "llm", [("model turn", "t"), ("writes text or asks", "d"), ("for a tool", "d")])
    s.node(1085, 455, 250, 84, "decide", [("tools", "t"), ("CheckAvailability", "m"), ("CalculateTotal", "m")])
    s.arrow([(835, 440), (960, 440)])
    s.label(898, 430, "tool request")
    s.arrow([(960, 474), (835, 474)], color="amber")
    s.label(898, 516, "result added to the chat")
    s.text(580, 534, "A turn with no tool request is the answer. Maximum 6 turns, then a safe message.", 12, "normal", SOFT)

    s.node(445, 455, 200, 84, "code", [("sources", "t"), ("SOURCES: line hidden", "d"), ("names checked", "d")])
    s.node(235, 455, 170, 84, "store", [("cache it", "t"), ("only if no tool", "d"), ("was used", "d")])
    s.node(75, 455, 120, 84, "end", [("done", "t"), ("sources", "d"), ("chips", "d")])
    s.arrow([(635, 455), (545, 455)])
    s.label(590, 445, "answer")
    s.arrow([(345, 455), (320, 455)])
    s.arrow([(150, 455), (137, 455)])

    s.text(30, 590, "While the loop runs, trail steps, product cards and answer tokens are sent to the browser as they happen.", 13, "normal", SOFT)
    legend(s, 650, [("llm", "calls the OpenAI API"), ("code", "plain code"), ("decide", "decides or acts"), ("store", "a store"), ("end", "start or end")])
    s.save("question-path.svg")


# ---------------------------------------------------------------- 3. evaluation
def evaluation():
    s = Svg(1280, 600, "How the evaluation works",
            "A fixed golden set of questions is answered by the pipeline and scored on four metrics. run_eval compares the "
            "averages with a saved baseline and flags drops over 0.1. ab_test runs two pipelines that differ only in their "
            "final-answer instruction, with the cache off, and compares their scores side by side.")
    header(s, "How answers are scored",
           "Offline, never on the live request path. Two commands share the golden set and the metrics.")

    def lane(y, title, cmd, pipe_lines, pipe_kind, tail_lines, tail_kind):
        s.text(30, y - 96, title, 16, "bold")
        s.text(30, y - 76, cmd, 12, "normal", SOFT, family=MONO)
        s.node(120, y, 170, 92, "end", [("golden set", "t"), ("5 questions", "d"), ("+ expected files", "d")])
        s.node(410, y, 250, 92, pipe_kind, pipe_lines)
        s.node(770, y, 300, 128, "decide", [("4 metrics per answer", "t"), ("faithfulness (LLM judge)", "d"),
                                            ("answer relevancy (LLM judge)", "d"), ("context precision (code)", "d"),
                                            ("context recall (LLM judge)", "d")])
        s.node(1120, y, 250, 92, tail_kind, tail_lines)
        s.arrow([(205, y), (285, y)])
        s.arrow([(535, y), (620, y)])
        s.arrow([(920, y), (995, y)])

    lane(190, "Regression check", "python -m src.evaluation.run_eval",
         [("RAGPipeline.answer()", "t"), ("one pipeline", "d"), ("use_cache=True", "m")], "code",
         [("regression.py", "t"), ("average vs saved baseline", "d"), ("drop over 0.1 = flagged", "m")], "decide")
    lane(410, "A/B test of two prompts", "python -m src.evaluation.ab_test",
         [("two pipelines, A and B", "t"), ("final instruction differs", "d"), ("use_cache=False", "m")], "code",
         [("side-by-side scores", "t"), ("A against B", "d"), ("printed, nothing saved", "m")], "end")
    s.text(30, 520, "The cache must be off for scoring: a cached answer returns no sources, so its context precision would be 0.", 13, "normal", SOFT)
    legend(s, 560, [("code", "plain code"), ("decide", "scores or decides"), ("end", "input or output")])
    s.save("evaluation-flow.svg")


if __name__ == "__main__":
    containers()
    question_path()
    evaluation()
