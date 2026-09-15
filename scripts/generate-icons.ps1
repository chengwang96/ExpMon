# Derives the UI logo, favicon and Windows icons from the hamster master PNG.
# Uses System.Drawing (Windows only); preserves the source alpha channel.
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BuildDir = Join-Path $Root "build"
$PublicDir = Join-Path $Root "public"
$PngDir = Join-Path $BuildDir "icons"
$SourcePath = Join-Path $Root "assets/expmon-hamster.png"
New-Item -ItemType Directory -Force -Path $BuildDir, $PublicDir, $PngDir | Out-Null

Add-Type -AssemblyName System.Drawing

function Write-IconPng {
  param([System.Drawing.Image]$Source, [int]$Size, [string]$OutPath)
  $bitmap = New-Object System.Drawing.Bitmap($Size, $Size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $attributes = New-Object System.Drawing.Imaging.ImageAttributes
  try {
    $graphics.Clear([System.Drawing.Color]::Transparent)
    $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
    $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $attributes.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
    $destination = [System.Drawing.Rectangle]::new(0, 0, $Size, $Size)
    $graphics.DrawImage($Source, $destination, 0, 0, $Source.Width, $Source.Height, [System.Drawing.GraphicsUnit]::Pixel, $attributes)
    $bitmap.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Host "wrote $OutPath ($Size x $Size)"
  } finally {
    $attributes.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
  }
}

$sizes = @(16, 24, 32, 48, 64, 128, 256)
$pngFiles = @()
$source = [System.Drawing.Image]::FromFile($SourcePath)
try {
  foreach ($size in $sizes) {
    $png = Join-Path $PngDir "icon-$size.png"
    Write-IconPng -Source $source -Size $size -OutPath $png
    $pngFiles += $png
  }
  Write-IconPng -Source $source -Size 512 -OutPath (Join-Path $BuildDir "icon.png")
  Write-IconPng -Source $source -Size 256 -OutPath (Join-Path $PublicDir "expmon-logo.png")
  Write-IconPng -Source $source -Size 128 -OutPath (Join-Path $PublicDir "favicon.png")
} finally {
  $source.Dispose()
}

# ICO entries contain PNG images at each Windows shell size.
$icoPath = Join-Path $BuildDir "icon.ico"
$stream = New-Object System.IO.MemoryStream
$writer = New-Object System.IO.BinaryWriter($stream)
try {
  $writer.Write([uint16]0)
  $writer.Write([uint16]1)
  $writer.Write([uint16]$sizes.Count)
  $offset = 6 + 16 * $sizes.Count
  for ($index = 0; $index -lt $sizes.Count; $index++) {
    $bytes = [System.IO.File]::ReadAllBytes($pngFiles[$index])
    $dimension = if ($sizes[$index] -ge 256) { 0 } else { $sizes[$index] }
    $writer.Write([byte]$dimension)
    $writer.Write([byte]$dimension)
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]32)
    $writer.Write([uint32]$bytes.Length)
    $writer.Write([uint32]$offset)
    $offset += $bytes.Length
  }
  foreach ($png in $pngFiles) {
    $writer.Write([System.IO.File]::ReadAllBytes($png))
  }
  $writer.Flush()
  [System.IO.File]::WriteAllBytes($icoPath, $stream.ToArray())
} finally {
  $writer.Dispose()
  $stream.Dispose()
}
Write-Host "wrote $icoPath ($($sizes.Count) sizes)"
