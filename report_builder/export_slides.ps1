$pptxPath = "E:\SEM 5 PROJECT\LexGuard-HTML\report_builder\LexGuard_UML_Architecture_Diagrams.pptx"
$outDir = "E:\SEM 5 PROJECT\LexGuard-HTML\report_builder\diagrams"

try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $prs = $ppt.Presentations.Open($pptxPath, $false, $false, $false)
    $names = @("fig_3_1_use_case.png", "fig_3_2_activity.png", "fig_3_3_state.png", "fig_3_4_sequence.png", "fig_3_5_er.png", "fig_3_6_dfd.png", "fig_3_7_architecture.png")
    
    for ($i = 1; $i -le $prs.Slides.Count; $i++) {
        $slide = $prs.Slides.Item($i)
        $outPath = Join-Path $outDir $names[$i - 1]
        $slide.Export($outPath, "PNG", 1920, 1440)
        Write-Output "Exported Slide $i -> $outPath"
    }
    $prs.Close()
    $ppt.Quit()
    Write-Output "ALL_SLIDES_EXPORTED_SUCCESSFULLY"
} catch {
    Write-Output "ERROR: $_"
}
