# Generates the ExpMon brand icon assets:
#   build/icon.svg  - vector source
#   build/icon.png  - 512px master PNG
#   build/icon.ico  - multi-size Windows icon (16..256, PNG-compressed entries)
#   public/favicon.png - web favicon (128px)
# Uses System.Drawing (Windows only) and writes the ICO container directly.
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BuildDir = Join-Path $Root "build"
$PublicDir = Join-Path $Root "public"
New-Item -ItemType Directory -Force -Path $BuildDir, $PublicDir | Out-Null

Add-Type -AssemblyName System.Drawing

function New-RoundRectPath {
  param([float]$X, [float]$Y, [float]$W, [float]$H, [float]$R)
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $d = $R * 2
  $path.AddArc($X, $Y, $d, $d, 180, 90)
  $path.AddArc($X + $W - $d, $Y, $d, $d, 270, 90)
  $path.AddArc($X + $W - $d, $Y + $H - $d, $d, $d, 0, 90)
  $path.AddArc($X, $Y + $H - $d, $d, $d, 90, 90)
  $path.CloseFigure()
  return $path
}

function New-ExpMonIcon {
  param([int]$Size, [string]$OutPath)
  $bmp = New-Object System.Drawing.Bitmap($Size, $Size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  try {
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)

    $unit = $Size / 100.0

    # Rounded tile with a teal gradient (brand --cyan #138a7e family).
    $tile = New-RoundRectPath -X 0 -Y 0 -W $Size -H $Size -R ($Size * 0.22)
    $gradient = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
      (New-Object System.Drawing.RectangleF(0, 0, $Size, $Size)),
      ([System.Drawing.ColorTranslator]::FromHtml("#1aa396")),
      ([System.Drawing.ColorTranslator]::FromHtml("#0b5f57")),
      [System.Drawing.Drawing2D.LinearGradientMode]::Vertical)
    $g.FillPath($gradient, $tile)
    $gradient.Dispose()
    $tile.Dispose()

    # Subtle node dots (hosts being monitored), low-opacity white.
    $nodeBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(58, 255, 255, 255))
    foreach ($nx in @(20, 34, 48, 62, 76)) {
      foreach ($ny in @(24, 74)) {
        $g.FillEllipse($nodeBrush, $nx * $unit - $Size * 0.022, $ny * $unit - $Size * 0.022, $Size * 0.044, $Size * 0.044)
      }
    }
    $nodeBrush.Dispose()

    # Heartbeat / activity pulse line (matches the UI brand mark).
    $pulse = [System.Drawing.Color]::White
    $pen = New-Object System.Drawing.Pen($pulse, ($Size * 0.078))
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $points = @(
      [System.Drawing.PointF]::new((14 * $unit), (50 * $unit)),
      [System.Drawing.PointF]::new((32 * $unit), (50 * $unit)),
      [System.Drawing.PointF]::new((40 * $unit), (22 * $unit)),
      [System.Drawing.PointF]::new((48 * $unit), (62 * $unit)),
      [System.Drawing.PointF]::new((56 * $unit), (50 * $unit)),
      [System.Drawing.PointF]::new((86 * $unit), (50 * $unit))
    )
    $g.DrawLines($pen, $points)
    $pen.Dispose()

    # Amber marker at the pulse peak (brand --amber #b66d16 family).
    $dotBrush = New-Object System.Drawing.SolidBrush([System.Drawing.ColorTranslator]::FromHtml("#d98a2b"))
    $dotR = $Size * 0.055
    $g.FillEllipse($dotBrush, 40 * $unit - $dotR, 22 * $unit - $dotR, $dotR * 2, $dotR * 2)
    $dotBrush.Dispose()

    $bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Host "wrote $OutPath ($Size x $Size)"
  } finally {
    $g.Dispose()
    $bmp.Dispose()
  }
}

$pngDir = Join-Path $BuildDir "icons"
New-Item -ItemType Directory -Force -Path $pngDir | Out-Null
$sizes = @(16, 24, 32, 48, 64, 128, 256)
$pngFiles = @()
foreach ($s in $sizes) {
  $png = Join-Path $pngDir "icon-$s.png"
  New-ExpMonIcon -Size $s -OutPath $png
  $pngFiles += $png
}
New-ExpMonIcon -Size 512 -OutPath (Join-Path $BuildDir "icon.png")
New-ExpMonIcon -Size 128 -OutPath (Join-Path $PublicDir "favicon.png")

# Assemble a Windows .ico (PNG-compressed entries, valid on Windows 10+).
$icoPath = Join-Path $BuildDir "icon.ico"
$count = $pngFiles.Count
$headerSize = 6 + 16 * $count
$stream = New-Object System.IO.MemoryStream
$writer = New-Object System.IO.BinaryWriter($stream)
$writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$count)
$offset = $headerSize
foreach ($png in $pngFiles) {
  $bytes = [System.IO.File]::ReadAllBytes($png)
  $dim = [System.Drawing.Image]::FromFile($png).Width
  $writer.Write([byte]($(if ($dim -ge 256) { 0 } else { $dim })))
  $writer.Write([byte]($(if ($dim -ge 256) { 0 } else { $dim })))
  $writer.Write([byte]0); $writer.Write([byte]0)
  $writer.Write([uint16]1); $writer.Write([uint16]32)
  $writer.Write([uint32]$bytes.Length); $writer.Write([uint32]$offset)
  $offset += $bytes.Length
}
foreach ($png in $pngFiles) {
  $writer.Write([System.IO.File]::ReadAllBytes($png))
}
$writer.Flush()
[System.IO.File]::WriteAllBytes($icoPath, $stream.ToArray())
$writer.Dispose(); $stream.Dispose()
Write-Host "wrote $icoPath ($count sizes)"
