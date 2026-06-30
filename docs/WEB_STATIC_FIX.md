
# Web static asset fix

The panel mounts `/assets` with `StaticFiles` before the SPA fallback. This prevents `/assets/*.css` and `/assets/*.js` from returning `index.html`, which caused browser errors such as `NS_ERROR_CORRUPTED_CONTENT`.

The `/favicon.ico` route has `response_model=None` and no union response annotation, so FastAPI/Pydantic will not try to build an invalid response model from `FileResponse | Response`.

The SPA fallback now returns 404 for missing API/static paths instead of returning HTML for CSS/JS/icon requests.



