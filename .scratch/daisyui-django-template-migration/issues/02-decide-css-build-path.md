# Decide how DaisyUI CSS enters production assets

Status: resolved
Type: grilling
Blocked by: 01

## Question

After reviewing the supported integration options, should this app compile Tailwind + daisyUI into a local static asset during its build/deploy flow, or depend on a remotely served stylesheet? Choose the production contract, including where the CSS build runs and how Django staticfiles/WhiteNoise serves its output. The recommendation is a local compiled asset: it keeps production rendering independent of a third-party CDN and fits the existing staticfiles pipeline, at the cost of adding a CSS build step.

## Answer

Use a locally compiled stylesheet produced by the official Tailwind standalone CLI with the matching daisyUI plugin bundle. Build it in CI or an image/build stage before Django `collectstatic`; write the generated CSS under `src/coda/apps/static/css/` and serve it through the existing Django staticfiles/WhiteNoise path. Pin compatible compiler/plugin artifacts; keep build-only inputs outside public static assets. This avoids a Node runtime dependency and a third-party CSS runtime dependency. Decision informed by the sibling [Choose a production-safe DaisyUI CSS delivery path](01-research-daisyui-css-delivery.md).