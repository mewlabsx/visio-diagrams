<#
  Visio-tier validation for a Python-generated .vsdx.

  The offline tier (test_vsdx_writer.py) already proves the package contract.
  This tier proves what only Visio can: that Master references resolve to real
  master instances, that the saved route is what the planner planned, and that
  glue is elastic (moving a node drags its connectors).

  COM permissions depend on the host. Use a bounded smoke test first;
  do not infer availability from a previous DSH session:
      $a = New-Object -ComObject Visio.InvisibleApp; $a.Version; $a.Quit()

  Usage:
      pwsh -NoProfile -File validate-vsdx.ps1 -Vsdx <file.vsdx> [-Planned <planned.json>] [-Report <out.json>]
#>
param(
  [Parameter(Mandatory)][string]$Vsdx,
  [string]$Planned,
  [string]$Report,
  [string]$PreviewPath
)
$ErrorActionPreference = 'Stop'
$Vsdx = (Resolve-Path -LiteralPath $Vsdx).Path
if (-not $Planned) { $Planned = [IO.Path]::ChangeExtension($Vsdx, '.planned.json') }
if (-not (Test-Path -LiteralPath $Planned)) { throw 'Planned JSON is required for acceptance' }
if ($Report -and (Test-Path -LiteralPath $Report)) { throw "Refusing to overwrite: $Report" }
if ($PreviewPath -and (Test-Path -LiteralPath $PreviewPath)) { throw "Refusing to overwrite: $PreviewPath" }

# --- preflight: orphan VISIO instances poison later stencil opens ------------
$orphans = @(Get-Process VISIO -ErrorAction SilentlyContinue | Where-Object { -not $_.MainWindowTitle })
if ($orphans.Count) {
  Write-Warning ("$($orphans.Count) invisible VISIO instance(s) already running (PIDs: " +
    (($orphans | ForEach-Object { $_.Id }) -join ', ') +
    "). If any holds a stencil, opening one will hang forever. Consider stopping them first.")
}

$result = [ordered]@{ vsdx = $Vsdx; planned = $Planned; status = 'FAIL' }
$app = $null; $doc = $null
try {
  $app = New-Object -ComObject Visio.InvisibleApp
  $app.AlertResponse = 7                      # suppress dialogs (else it can hang)

  $sw = [Diagnostics.Stopwatch]::StartNew()
  $doc = $app.Documents.OpenEx($Vsdx, 0)      # a repair prompt means the package is wrong
  $pg = $doc.Pages.Item(1)
  $result.openMs = [int]$sw.Elapsed.TotalMilliseconds
  $PH = [double]$pg.PageSheet.CellsU('PageHeight').ResultIU

  $result.pageWidth  = [double]$pg.PageSheet.CellsU('PageWidth').ResultIU
  $result.pageHeight = $PH
  $result.shapes     = $pg.Shapes.Count
  $result.connects   = $pg.Connects.Count

  # --- master resolution: proves these are real master instances -------------
  $src = [ordered]@{}
  foreach ($s in $pg.Shapes) {
    $m = '(self-drawn)'
    try { if ($s.Master) { $m = $s.Master.NameU } } catch {}
    if ($src.Contains($m)) { $src[$m] = $src[$m] + 1 } else { $src[$m] = 1 }
  }
  $result.shapeSources = $src
  if ($PreviewPath) {
    $pg.Export([IO.Path]::GetFullPath($PreviewPath))
    $result.preview = [IO.Path]::GetFullPath($PreviewPath)
  }

  # --- route fidelity, for every planned edge -------------------------------
  try {
  if (Test-Path -LiteralPath $Planned) {
    $plan = Get-Content -LiteralPath $Planned -Raw -Encoding UTF8 | ConvertFrom-Json
    $result.plannedEdges = @($plan.edges).Count
    $result.expectedConnects = 2 * @($plan.edges).Count
    $result.expectedShapes = @($plan.nodes).Count + @($plan.edges).Count + @($plan.edges | Where-Object { $_.label -and $_.text }).Count
    if ($plan.page.title) { $result.expectedShapes++ }
    $result.textNodesChecked = 0
    $result.maxFontSizeDeviationPt = 0.0
    foreach ($nodePlan in $plan.nodes) {
      $nodeShape = $pg.Shapes.ItemU("node_$($nodePlan.id)")
      $wantedPt = if ($nodePlan.fontSize) { [double]$nodePlan.fontSize } else { 11.0 }
      $actualPt = [double]$nodeShape.CellsU('Char.Size').ResultIU * 72.0
      $result.maxFontSizeDeviationPt = [Math]::Max($result.maxFontSizeDeviationPt, [Math]::Abs($actualPt-$wantedPt))
      if (([string]$nodeShape.Text).TrimEnd([char[]]"`r`n") -ne ([string]$nodePlan.text).TrimEnd([char[]]"`r`n")) { throw "Text mismatch: $($nodePlan.id)" }
      $result.textNodesChecked++
    }
    $result.expectedRouteVertices = 0
    foreach ($edgePlan in $plan.edges) { $result.expectedRouteVertices += @($edgePlan.routePoints).Count }
    $worst = 0.0; $checked = 0
    $i = 0
    foreach ($e in $plan.edges) {
      $i++
      $line = $null
      try { $line = $pg.Shapes.ItemU("edge_$i") } catch {}
      if (-not $line) { throw "Missing edge_$i" }
      $rows = $line.RowCount(10)
      $want = @($e.routePoints)
      if ($want.Count -lt 2) { throw "edge_$i has no independently planned route" }
      $n = [Math]::Min($rows - 1, $want.Count)
      for ($j = 1; $j -le $n; $j++) {
        $lx = $line.CellsSRC(10, $j, 0).ResultIU
        $ly = $line.CellsSRC(10, $j, 1).ResultIU
        $px = 0.0; $py = 0.0
        $line.XYToPage($lx, $ly, [ref]$px, [ref]$py)
        $wx = [double]$want[$j - 1][0]
        $wy = $PH - [double]$want[$j - 1][1]
        $worst = [Math]::Max($worst, [Math]::Abs($px - $wx))
        $worst = [Math]::Max($worst, [Math]::Abs($py - $wy))
        $checked++
      }
    }
    $result.routeVerticesChecked = $checked
    $result.maxRouteDeviationIn  = [Math]::Round($worst, 6)
    $result.containerChecks = @()
    foreach ($containerPlan in @($plan.nodes | Where-Object { $_.kind -eq 'container' })) {
      $containerShape = $pg.Shapes.ItemU("node_$($containerPlan.id)")
      $expected = @($plan.nodes | Where-Object { $_.parent -eq $containerPlan.id } | ForEach-Object { [int]$pg.Shapes.ItemU("node_$($_.id)").ID } | Sort-Object)
      $allMembers = @($containerShape.ContainerProperties.GetMemberShapes(16))
      # Visio may attach internal connectors/labels as auxiliary members.
      # Check the explicit business-node hierarchy exactly, and report auxiliaries.
      $actual = @($allMembers | Where-Object { $pg.Shapes.ItemFromID([int]$_).NameU -like 'node_*' } | Sort-Object)
      if (($actual -join ',') -ne ($expected -join ',')) { throw "Native container membership mismatch: $($containerPlan.id), actual=$($actual -join ','), expected=$($expected -join ',')" }
      $result.containerChecks += @{ id=$containerPlan.id; members=$actual; auxiliaryMembers=@($allMembers | Where-Object { $pg.Shapes.ItemFromID([int]$_).NameU -notlike 'node_*' }) }
    }
  }
  } catch { $result.routeCheckError = $_.Exception.Message }

  # --- glue elasticity: move a node, its connectors must follow -------------
  # Each check is guarded so one failure cannot discard the whole report.
  try {
    if ((Test-Path -LiteralPath $Planned) -and @($plan.edges).Count -gt 0) {
      $e0 = $plan.edges[0]
      # nodes are named node_<id> by render-visio.ps1; tolerate the bare id too
      $node = $null
      foreach ($cand in @("node_$($e0.from)", [string]$e0.from)) {
        try { $node = $pg.Shapes.ItemU($cand); break } catch {}
      }
      $edge = $pg.Shapes.ItemU('edge_1')
      if ($node -and $edge) {
        $before = $edge.CellsU('BeginX').ResultIU
        $node.CellsU('PinX').ResultIU = $node.CellsU('PinX').ResultIU + 0.3
        $result.moveNode = [string]$e0.from
        $result.moveDeltaIn = [Math]::Round($edge.CellsU('BeginX').ResultIU - $before, 6)
        $result.moveExpectedIn = 0.3
      }
      else { $result.moveCheckError = "shape not found for node '$($e0.from)'" }
    }
  }
  catch { $result.moveCheckError = $_.Exception.Message }

  try {
    $result.containerMoveChecks = @()
    $containers = @($plan.nodes | Where-Object { $_.kind -eq 'container' })
    if ($containers.Count) {
      # StructureBasic preserves existing membership; default COM services are disabled.
      $doc.DiagramServicesEnabled = 2
      $nodePlans = @{}; foreach ($n in $plan.nodes) { $nodePlans[[string]$n.id]=$n }
      foreach ($n in $plan.nodes) {
        if($n.parent -and (-not $nodePlans.ContainsKey([string]$n.parent) -or $nodePlans[[string]$n.parent].kind -ne 'container')){throw "Invalid parent in planned JSON: $($n.id)"}
      }
      foreach ($containerPlan in $containers) {
        $before = @{}
        foreach ($n in $plan.nodes) { $before[[string]$n.id]=[double]$pg.Shapes.ItemU("node_$($n.id)").CellsU('PinX').ResultIU }
        $containerShape=$pg.Shapes.ItemU("node_$($containerPlan.id)")
        $selection=$pg.CreateSelection(0);$selection.Select($containerShape,2);$selection.Move(0.3,0)
        $descendants=0
        foreach ($n in $plan.nodes) {
          $current=[string]$n.id;$affected=$current -eq $containerPlan.id
          $visited=@{}
          while ($nodePlans[$current].parent) {
            if($visited.ContainsKey($current)){throw 'Cycle in planned container hierarchy'}
            $visited[$current]=$true
            $current=[string]$nodePlans[$current].parent
            if($current -eq $containerPlan.id){$affected=$true}
          }
          $expected=if($affected){0.3}else{0.0}
          $actual=[double]$pg.Shapes.ItemU("node_$($n.id)").CellsU('PinX').ResultIU-$before[[string]$n.id]
          if([Math]::Abs($actual-$expected) -gt 0.001){throw "Container movement mismatch: $($containerPlan.id) -> $($n.id)"}
          if($affected -and $n.id -ne $containerPlan.id){$descendants++}
        }
        $selection.Move(-0.3,0)
        $result.containerMoveChecks+=@{id=$containerPlan.id;descendantsChecked=$descendants;deltaIn=0.3;status='PASS'}
      }
    }
  } catch { $result.containerMoveCheckError=$_.Exception.Message }

  $doc.Saved = $true; $doc.Close(); $doc = $null
}
catch {
  $result.error = $_.Exception.Message
}
finally {
  if ($doc) { try { $doc.Saved = $true; $doc.Close() } catch {} }
  if ($app) { try { $app.Quit() } catch {} }
}

# --- verdict (always runs, so a partial failure still yields a full report) --
$ok = $true
$why = @()
if ($result.error) { $ok = $false; $why += "error: $($result.error)" }
if ($result.routeCheckError) { $ok = $false; $why += "route check: $($result.routeCheckError)" }
if ($result.moveCheckError)  { $ok = $false; $why += "move check: $($result.moveCheckError)" }
if ($result.containerMoveCheckError) { $ok=$false; $why+="container movement: $($result.containerMoveCheckError)" }
if ($null -eq $result.shapes -or $result.shapes -ne $result.expectedShapes) { $ok = $false; $why += 'shape count missing or incorrect' }
if ($null -eq $result.routeVerticesChecked -or $result.routeVerticesChecked -ne $result.expectedRouteVertices) { $ok = $false; $why += 'route coverage incomplete' }
if ($result.expectedConnects -gt 0 -and $null -eq $result.moveDeltaIn) { $ok = $false; $why += 'move test missing' }
if ($null -eq $result.textNodesChecked -or $result.textNodesChecked -ne @($plan.nodes).Count) { $ok = $false; $why += 'text coverage incomplete' }
if ($null -eq $result.maxFontSizeDeviationPt -or $result.maxFontSizeDeviationPt -gt 0.01) { $ok = $false; $why += 'actual font sizes differ from specification' }
if ($result.openMs -gt 30000) { $ok = $false; $why += 'open took too long' }
if ($result.connects -ne $result.expectedConnects) {
  $ok = $false; $why += "connects $($result.connects) != expected $($result.expectedConnects)"
}
if ($null -ne $result.maxRouteDeviationIn -and $result.maxRouteDeviationIn -gt 0.001) {
  $ok = $false; $why += "route deviation $($result.maxRouteDeviationIn) in"
}
if ($null -ne $result.moveDeltaIn -and [Math]::Abs($result.moveDeltaIn - 0.3) -gt 0.001) {
  $ok = $false; $why += "glue not elastic (delta $($result.moveDeltaIn), want 0.3)"
}
$result.status = if ($ok) { 'PASS' } else { 'FAIL' }
if ($why.Count) { $result.reasons = $why }

$json = $result | ConvertTo-Json -Depth 6
if ($Report) { $json | Set-Content -LiteralPath $Report -Encoding utf8 }
Write-Output $json
if ($result.status -ne 'PASS') { exit 1 } else { exit 0 }
