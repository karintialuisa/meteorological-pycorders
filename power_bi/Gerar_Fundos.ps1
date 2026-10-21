Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = 'Stop'

function New-ReportBackground {
    param([string]$Page, [string]$Accent, [string]$Output, [string[]]$Metrics, [string[]]$Charts)

    $bitmap = [System.Drawing.Bitmap]::new(1600, 900)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

    function Fill-Box {
        param([string]$Color, [int]$X, [int]$Y, [int]$Width, [int]$Height)
        $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($Color))
        $graphics.FillRectangle($brush, $X, $Y, $Width, $Height)
        $brush.Dispose()
    }

    function Write-Label {
        param([string]$Text, [int]$X, [int]$Y, [int]$Size, [string]$Color, [bool]$Bold = $false)
        $style = [System.Drawing.FontStyle]::Regular
        if ($Bold) { $style = [System.Drawing.FontStyle]::Bold }
        $font = [System.Drawing.Font]::new('Segoe UI', $Size, $style, [System.Drawing.GraphicsUnit]::Pixel)
        $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($Color))
        $graphics.DrawString($Text, $font, $brush, $X, $Y)
        $font.Dispose()
        $brush.Dispose()
    }

    try {
        $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#F3F6F5'))
        Fill-Box '#202B29' 0 0 208 900
        Fill-Box $Accent 24 36 5 30
        Write-Label 'PYCORDERS' 40 36 21 '#FFFFFF' $true
        Write-Label 'DADOS AMBIENTAIS' 24 84 12 '#B2C4BE'
        Write-Label 'PAINEIS' 24 170 12 '#B2C4BE'
        $selectedY = 210
        if ($Page -ne 'Meteorologia') { $selectedY = 270 }
        Fill-Box '#34453F' 12 $selectedY 184 48
        Fill-Box $Accent 12 $selectedY 4 48
        Write-Label 'Meteorologia' 28 223 16 '#FFFFFF'
        Write-Label 'Qualidade da Agua' 28 283 16 '#FFFFFF'
        Write-Label 'LOCALIZACAO' 24 748 12 '#B2C4BE'
        Write-Label 'Estado / Cidade / Estacao' 24 775 12 '#B2C4BE'
        Fill-Box $Accent 240 34 36 4
        Write-Label $Page 240 52 30 '#202B29' $true
        Write-Label 'MONITORAMENTO AMBIENTAL' 240 94 12 '#52675F'

        $filterLabels = @('ESTADO', 'CIDADE', 'ESTACAO', 'PERIODO')
        for ($index = 0; $index -lt 4; $index++) {
            $left = 240 + 336 * $index
            Write-Label $filterLabels[$index] $left 132 12 '#52675F' $true
            Fill-Box '#FFFFFF' $left 156 320 40
            Fill-Box '#DCE5E1' $left 195 320 1
            Fill-Box '#FFFFFF' $left 220 320 110
            Fill-Box $Accent $left 220 320 3
            Write-Label $Metrics[$index] ($left + 16) 237 15 '#52675F'
        }

        Fill-Box '#DCE5E1' 240 354 1328 1
        Write-Label $Charts[0] 240 373 18 '#202B29' $true
        Write-Label $Charts[1] 920 373 18 '#202B29' $true
        Fill-Box '#DCE5E1' 240 660 1328 1
        Write-Label 'Detalhamento das leituras' 240 679 18 '#202B29' $true
        Fill-Box '#DCE5E1' 240 859 1328 1
        Write-Label 'PYCORDERS  /  SILVER' 240 873 11 '#52675F'
        Write-Label 'MONITORAMENTO AMBIENTAL' 1354 873 11 '#52675F'
        $bitmap.Save((Join-Path $PSScriptRoot $Output), [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

New-ReportBackground -Page 'Meteorologia' -Accent '#167A58' -Output 'fundo_meteorologia.png' `
    -Metrics @('Estacoes com leituras', 'Temperatura media (C)', 'Umidade media (%)', 'Chuva media por leitura (mm)') `
    -Charts @('Temperatura do ar ao longo do tempo', 'Umidade ao longo do tempo')

New-ReportBackground -Page 'Qualidade da Agua' -Accent '#087F8C' -Output 'fundo_qualidade_agua.png' `
    -Metrics @('Estacoes com leituras', 'Temperatura media (C)', 'pH medio', 'Oxigenio medio') `
    -Charts @('pH ao longo do tempo', 'Oxigenio ao longo do tempo')

Write-Output 'Fundos PNG gerados em 1600 x 900.'