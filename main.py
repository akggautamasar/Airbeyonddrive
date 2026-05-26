# ═══════════════════════════════════════════════════════════════════════════════
# RESTRICTED CONTENT IMPORT — paste these 3 endpoints at the END of main.py,
# just before the `if __name__ == "__main__":` line (or anywhere after the
# existing smart_bulk_import endpoints).
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/restrictedImport")
async def restricted_import(request: Request):
    """
    Start a restricted-content import as a background task and return import_id.
    Frontend polls /api/getRestrictedProgress with the returned id.

    Body:
      password: admin password
      path:     destination folder in the drive
      links:    multi-line string. Each line = a single link OR `link1 - link2` range
    """
    from utils.restricted_import import (
        RESTRICTED_IMPORT_MANAGER, RESTRICTED_PROGRESS, parse_input_lines,
    )
    from utils.clients import get_client
    import secrets as _secrets

    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    logger.info(f"restrictedImport request")

    links_text = (data.get("links") or "").strip()
    if not links_text:
        return JSONResponse({"status": "error", "message": "No links provided"})

    try:
        jobs = parse_input_lines(links_text)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

    if not jobs:
        return JSONResponse({"status": "error", "message": "No valid links"})

    # Need a USER client (premium/regular) — bot cannot read restricted content
    try:
        user_client = get_client(premium_required=True)
    except Exception:
        return JSONResponse({
            "status": "error",
            "message": "No user account configured. Restricted import requires a "
                       "logged-in user session that is a member of the source channel."
        })

    bot_client = get_client()  # any bot for uploading to STORAGE_CHANNEL
    destination_folder = data["path"]
    import_id = _secrets.token_hex(8)

    async def _run():
        try:
            await RESTRICTED_IMPORT_MANAGER.run(
                user_client, bot_client, jobs, destination_folder, import_id,
            )
        except Exception as e:
            logger.error(f"Background restricted import error: {e}")
            RESTRICTED_PROGRESS[import_id] = RESTRICTED_PROGRESS.get(import_id, {})
            RESTRICTED_PROGRESS[import_id]["status"] = "error"
            RESTRICTED_PROGRESS[import_id]["error_msg"] = str(e)

    task = asyncio.create_task(_run())
    if not hasattr(app.state, "restricted_tasks"):
        app.state.restricted_tasks = set()
    app.state.restricted_tasks.add(task)
    task.add_done_callback(app.state.restricted_tasks.discard)

    return JSONResponse({
        "status": "started",
        "import_id": import_id,
        "total_jobs": len(jobs),
    })


@app.post("/api/getRestrictedProgress")
async def get_restricted_progress(request: Request):
    """Poll progress of a running or completed restricted import."""
    from utils.restricted_import import RESTRICTED_PROGRESS

    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    import_id = data.get("import_id")
    if not import_id or import_id not in RESTRICTED_PROGRESS:
        return JSONResponse({"status": "not found"})

    return JSONResponse({"status": "ok", "data": RESTRICTED_PROGRESS[import_id]})


@app.post("/api/cancelRestrictedImport")
async def cancel_restricted_import(request: Request):
    """Cancel a running restricted import."""
    from utils.restricted_import import RESTRICTED_CANCEL

    data = await request.json()
    if data.get("password") != ADMIN_PASSWORD:
        return JSONResponse({"status": "Invalid password"})

    import_id = data.get("import_id")
    if import_id:
        RESTRICTED_CANCEL.add(import_id)
        return JSONResponse({"status": "ok", "message": "Cancel signal sent"})
    return JSONResponse({"status": "error", "message": "import_id required"})
