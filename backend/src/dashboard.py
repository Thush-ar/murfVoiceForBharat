from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from memory_db import get_call_stats


app = FastAPI(title="Palo Call Analytics")


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API: Call statistics
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def stats():
    """
    Return only aggregate Day 8 analytics.

    No caller information, transcripts, questions, answers,
    user IDs, or other sensitive information is exposed.
    """

    data = await get_call_stats()

    return {
        "total": data["total"],
        "successful": data["successful"],
        "failed": data["failed"],
    }


# ---------------------------------------------------------------------------
# Dashboard webpage
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>

<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Palo | Call Analytics</title>

    <style>

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;

            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;

            background: #f5f7fb;
            color: #172033;
        }

        .container {
            width: min(1100px, 92%);
            margin: 0 auto;
            padding: 60px 0;
        }

        .header {
            margin-bottom: 40px;
        }

        .brand {
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: #667085;
            margin-bottom: 10px;
        }

        h1 {
            margin: 0;
            font-size: 38px;
            line-height: 1.1;
        }

        .subtitle {
            margin-top: 12px;
            color: #667085;
            font-size: 16px;
        }

        .cards {
            display: grid;
            grid-template-columns:
                repeat(3, minmax(0, 1fr));

            gap: 20px;
        }

        .card {
            background: white;
            border-radius: 20px;
            padding: 28px;

            border: 1px solid #e5e7eb;

            box-shadow:
                0 8px 30px rgba(16, 24, 40, 0.06);
        }

        .card-label {
            font-size: 14px;
            font-weight: 600;
            color: #667085;
            margin-bottom: 14px;
        }

        .number {
            font-size: 52px;
            line-height: 1;
            font-weight: 750;
        }

        .status {
            margin-top: 40px;

            background: white;
            border-radius: 16px;
            padding: 18px 22px;

            border: 1px solid #e5e7eb;

            color: #667085;
            font-size: 14px;
        }

        .status-dot {
            display: inline-block;

            width: 8px;
            height: 8px;

            border-radius: 50%;

            background: #22c55e;

            margin-right: 8px;
        }

        @media (max-width: 700px) {

            .cards {
                grid-template-columns: 1fr;
            }

            h1 {
                font-size: 30px;
            }

            .container {
                padding: 35px 0;
            }
        }

    </style>

</head>


<body>

    <main class="container">

        <header class="header">

            <div class="brand">
                PALO
            </div>

            <h1>
                Call Analytics
            </h1>

            <div class="subtitle">
                Learning &amp; Literacy · Day 8
            </div>

        </header>


        <section class="cards">

            <div class="card">

                <div class="card-label">
                    Total Calls
                </div>

                <div
                    class="number"
                    id="total"
                >
                    —
                </div>

            </div>


            <div class="card">

                <div class="card-label">
                    Successful Calls
                </div>

                <div
                    class="number"
                    id="successful"
                >
                    —
                </div>

            </div>


            <div class="card">

                <div class="card-label">
                    Failed Calls
                </div>

                <div
                    class="number"
                    id="failed"
                >
                    —
                </div>

            </div>

        </section>


        <div class="status">

            <span class="status-dot"></span>

            Connected to live call data

            · Last updated:
            <span id="updated">
                —
            </span>

        </div>

    </main>


    <script>

        async function loadStats() {

            try {

                const response =
                    await fetch("/api/stats");

                if (!response.ok) {
                    throw new Error(
                        "Failed to load statistics"
                    );
                }

                const data =
                    await response.json();


                document.getElementById("total")
                    .textContent = data.total;

                document.getElementById("successful")
                    .textContent = data.successful;

                document.getElementById("failed")
                    .textContent = data.failed;


                document.getElementById("updated")
                    .textContent =
                        new Date().toLocaleTimeString();

            }

            catch (error) {

                console.error(
                    "Dashboard error:",
                    error
                );

            }

        }


        // Load immediately.
        loadStats();


        // Automatically refresh every 2 seconds.
        setInterval(
            loadStats,
            2000
        );

    </script>

</body>

</html>
"""


# ---------------------------------------------------------------------------
# Local development entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "dashboard:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
