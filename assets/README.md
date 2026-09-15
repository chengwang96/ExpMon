# ExpMon Brand Assets

`expmon-hamster.png` is the canonical hamster logo, generated with the built-in
`image_gen` tool using the DSH project's `assets/icon-1024.png` as a style reference.
It has a transparent exterior, a white rounded tile and a teal hamster mark.
DSH is a reference only, not a build dependency.

Run `npm run desktop:icons` on Windows to derive these assets from the master PNG:

- `public/expmon-logo.png`: 256px UI and README logo.
- `public/favicon.png`: 128px browser favicon.
- `build/icon.png`: 512px desktop icon.
- `build/icon.ico`: Windows icon containing 16, 24, 32, 48, 64, 128 and 256px images.

The generator only resizes and packages the source, preserving transparency.
Keep the master and generated assets in sync when updating the logo.

## Original Generation Prompt

Use case: logo-brand. Edit the provided DSH app-icon reference into its companion
ExpMon application icon. The reference is for the polished, restrained visual
family: a very light cool porcelain rounded-square tile with transparent exterior,
one large clean animal silhouette, generous and balanced margins, and no text.
Replace the cat entirely with ONE unmistakable small hamster. Hamster: compact
sitting body, very round head with plump cheek pouches, small rounded ears, two
short front paws tucked together at its chest, short back feet, no visible long
tail. A calm, alert, quietly friendly expression, facing forward with a very slight
three-quarter turn. Make this an elegant, minimal, vector-like brand mark rather
than a detailed cartoon or furry illustration. Use a deep muted teal (#166C63
family) for the main silhouette, with only a few broad negative-space cutouts for
the pale belly, inner ears and face; simple small eyes and nose. Keep all contours
bold and smooth and the form recognizable at 24-32 pixels. The reference's cat must
not remain. Preserve the restrained light cool rounded-square tile style, but use
a nearly flat soft off-white/pale mint surface (#F0F6F4 family), very subtle surface
depth at most. A square 1024x1024 PNG, entire tile and mascot fully visible,
approximately 6% transparent margin outside the tile, true transparent alpha
outside the rounded square (not a black, white, or checkerboard background). The
hamster should occupy about 70% of the canvas height and have a strong recognizable
silhouette. No letters, no wordmark, no monitor, no charts, no running wheel, no
accessories, no food, no extra objects, no whisker filigree, no glossy 3D rendering,
no long ears, no cat-like pointed ears, no thin details, no watermark. Deliver only
one final icon, not a contact sheet or mockup.

## White Background Edit

The current source was edited with the built-in `image_gen` tool using this prompt:

Use case: precise-object-edit. Edit this exact existing ExpMon hamster app icon.
Change ONLY the pale mint/off-white rounded-square tile background to clean,
completely flat pure white (#FFFFFF, RGB 255 255 255). Remove all mint tint,
shading, gradients and texture from the tile. The pale negative-space areas of
the hamster (cheeks, belly, inner ears, feet, eye highlights) should also be pure
white so the mark remains a consistent two-color teal-and-white design. Preserve
the hamster's exact silhouette, face, eyes, nose, mouth, paws, ears, proportions,
pose, position, size, contour details and teal color. Preserve the rounded-square
shape and the transparent margin outside it. True transparent alpha outside the
tile, not a black background and not a checkerboard. Keep the current framing and
square canvas. Do not redesign or restyle the hamster. No new objects, no text,
no additional colors, no shadow. Return just the finished white-background icon.
