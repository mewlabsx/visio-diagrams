param(
  [Parameter(Mandatory)][string]$SpecPath,
  [Parameter(Mandatory)][string]$OutputPath,
  [ValidateSet('spec','on','off')][string]$ColorFill='spec',
  [ValidateSet('python','com')][string]$Backend='python',
  [string]$StencilPath
)
$ErrorActionPreference='Stop'
if($Backend -eq 'python'){
  $nativeArgs=@('-X','utf8',(Join-Path $PSScriptRoot 'render_native.py'),$SpecPath,$OutputPath,'--color-fill',$ColorFill)
  if($StencilPath){$nativeArgs+=@('--stencil',$StencilPath)}
  & python @nativeArgs
  if($LASTEXITCODE -ne 0){throw 'Python VSDX generation failed; output is not accepted'}
  return
}
$spec=Get-Content -LiteralPath $SpecPath -Raw -Encoding utf8 | ConvertFrom-Json
if($StencilPath){$spec.page | Add-Member -NotePropertyName stencilPath -NotePropertyValue $StencilPath -Force}
if($spec.localLayout -or @($spec.edges | Where-Object routeGroup).Count){
  $planned=[IO.Path]::ChangeExtension([IO.Path]::GetFullPath($OutputPath),'.planned.json')
  if(Test-Path -LiteralPath $planned){throw "Refusing to overwrite: $planned"}
  [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($planned)) | Out-Null
  $planner=if($spec.localLayout){'local_layout.py'}else{'plan_routes.py'}
  & python -X utf8 (Join-Path $PSScriptRoot $planner) $SpecPath $planned
  if($LASTEXITCODE -ne 0){throw "Layout/routing failed; inspect $planned and its .failure.json diagnostic"}
  $spec=Get-Content -LiteralPath $planned -Raw -Encoding utf8 | ConvertFrom-Json
}
$useColor=if($ColorFill -eq 'on'){$true}elseif($ColorFill -eq 'off'){$false}elseif($null -ne $spec.page.colorFill){if($spec.page.colorFill -isnot [bool]){throw 'page.colorFill must be boolean'};$spec.page.colorFill}else{$true}
$out=[IO.Path]::GetFullPath($OutputPath)
if([IO.Path]::GetExtension($out) -ne '.vsdx'){throw 'OutputPath must end in .vsdx'}
$png=[IO.Path]::ChangeExtension($out,'.png')
$report=[IO.Path]::ChangeExtension($out,'.validation.json')
foreach($p in @($out,$png,$report)){if(Test-Path -LiteralPath $p){throw "Refusing to overwrite: $p"}}
$width=[double]$spec.page.width; $height=[double]$spec.page.height
if($width -le 0 -or $height -le 0){throw 'Invalid page size'}
$ids=@{}; $warnings=[Collections.Generic.List[string]]::new()
foreach($n in $spec.nodes){
  if(-not $n.id -or $ids.ContainsKey([string]$n.id)){throw 'Empty or duplicate node id'}
  $ids[[string]$n.id]=$true
  foreach($key in @('x','y','w','h')){if($null -eq $n.$key){throw "Missing $key on $($n.id)"}}
  if($n.x -lt 0 -or $n.y -lt 0 -or $n.w -le 0 -or $n.h -le 0 -or ($n.x+$n.w) -gt $width -or ($n.y+$n.h) -gt $height){throw "Node outside page: $($n.id)"}
  if($n.kind -and $n.kind -notin @('box','container','text','ellipse','diamond','terminator')){throw "Unsupported kind: $($n.kind)"}
  if($n.fill -and $n.fill -notmatch '^#[0-9a-fA-F]{6}$'){throw "Invalid fill: $($n.id)"}
  if($null -ne $n.fontSize -and $n.fontSize -le 0){throw 'Invalid fontSize'}
  $fs=if($n.fontSize){[double]$n.fontSize}else{11.0}
  $lines=([string]$n.text) -split "`n"
  foreach($line in $lines){if($line.Length*$fs/72 -gt ([double]$n.w-0.1)){$warnings.Add("Possible text width overflow: $($n.id)");break}}
  if($lines.Count*$fs*1.3/72 -gt [double]$n.h){$warnings.Add("Possible text height overflow: $($n.id)")}
}
foreach($e in $spec.edges){
  foreach($port in @($e.fromPort,$e.toPort)){if($port -and $port -notin @('top','bottom','left','right')){throw "Invalid port: $port"}}
  if(-not $ids.ContainsKey([string]$e.from) -or -not $ids.ContainsKey([string]$e.to)){throw 'Unknown edge endpoint'}
  if($e.label){$l=$e.label; if($null -eq $l.x -or $null -eq $l.y -or $l.x -lt 0 -or $l.y -lt 0 -or $l.w -le 0 -or $l.h -le 0 -or ($l.x+$l.w) -gt $width -or ($l.y+$l.h) -gt $height){throw 'Invalid edge label geometry'}}
}
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($out)) | Out-Null
$app=$null; $doc=$null; $verified=$null; $stencil=$null; $sources=@{}
function Set-Cell($shape,[string]$name,[string]$formula){$shape.CellsU($name).FormulaU=$formula}
function Glue-Port($cell,$shape,$port,$fraction=.5){
  if($null -eq $fraction){$fraction=.5}
  if(-not $port){$cell.GlueTo($shape.CellsU('PinX'));return}
  $xy=switch($port){'top'{@($fraction,1.0)}'bottom'{@($fraction,0.0)}'left'{@(0.0,(1-$fraction))}'right'{@(1.0,(1-$fraction))}}
  $cell.GlueToPos($shape,[double]$xy[0],[double]$xy[1])
}
function Style-Shape($s,$n){
  $s.Text=[string]$n.text
  $fill=if($useColor -and $n.fill){$n.fill}else{'#FFFFFF'}
  $r=[Convert]::ToInt32($fill.Substring(1,2),16);$g=[Convert]::ToInt32($fill.Substring(3,2),16);$b=[Convert]::ToInt32($fill.Substring(5,2),16)
  Set-Cell $s 'FillForegnd' "RGB($r,$g,$b)"
  Set-Cell $s 'FillPattern' '1'
  Set-Cell $s 'LineColor' 'RGB(64,64,64)'
  Set-Cell $s 'LineWeight' '0.75 pt'
  Set-Cell $s 'Rounding' '0 in'
  if($n.kind -eq 'terminator'){Set-Cell $s 'Rounding' "$([Math]::Min([double]$n.w,[double]$n.h)/2) in"}
  Set-Cell $s 'ShdwPattern' '0'
  Set-Cell $s 'Char.Font' 'FONT("Microsoft YaHei")'
  Set-Cell $s 'Char.AsianFont' 'FONT("Microsoft YaHei")'
  $fs=if($n.fontSize){$n.fontSize}else{11}
  Set-Cell $s 'Char.Size' "$fs pt"
  Set-Cell $s 'Char.Color' 'RGB(0,0,0)'
  Set-Cell $s 'Para.HorzAlign' '1'
  Set-Cell $s 'VerticalAlign' '1'
  if($n.bold -or $n.kind -eq 'container'){Set-Cell $s 'Char.Style' '1'}
  if($n.kind -eq 'container'){Set-Cell $s 'VerticalAlign' '0';Set-Cell $s 'TopMargin' '0.08 in'}
  if($n.kind -eq 'text'){Set-Cell $s 'FillPattern' '0';Set-Cell $s 'LinePattern' '0'}
  elseif($n.dashed){Set-Cell $s 'LinePattern' '2'}
}
try {
  $app=New-Object -ComObject Visio.InvisibleApp
  $app.AlertResponse=7
  $doc=$app.Documents.Add('')
  $stencilPath=if($spec.page.stencilPath){[string]$spec.page.stencilPath}else{Join-Path $app.Path 'Visio Content\2052\BASFLO_M.VSSX'}
  if(Test-Path -LiteralPath $stencilPath){$stencil=$app.Documents.OpenEx($stencilPath,64)}else{$warnings.Add('Stencil unavailable; using self-drawn fallback')}
  $page=$doc.Pages.Item(1)
  Set-Cell $page.PageSheet 'PageWidth' "$width in"
  Set-Cell $page.PageSheet 'PageHeight' "$height in"
  $map=@{}; $expected=@{}
  foreach($n in $spec.nodes){
    $x=[double]$n.x;$y=$height-[double]$n.y;$w=[double]$n.w;$h=[double]$n.h
    $masterName=if($n.master){[string]$n.master}elseif($spec.page.diagramType -eq 'flowchart'){switch($n.kind){'diamond'{'Decision'}'terminator'{'Start/End'}'box'{'Process'}default{if(-not $n.kind){'Process'}}}}
    $master=$null
    if($masterName -and $stencil){try{$master=$stencil.Masters.ItemU($masterName)}catch{$warnings.Add("Master unavailable: $masterName; fallback")}}
    if($master){
      $s=$page.Drop($master,($x+$w/2),($y-$h/2))
      Set-Cell $s 'Width' "$w in";Set-Cell $s 'Height' "$h in"
      $sources[[string]$n.id]=@{type='stencil';path=$stencilPath;master=$master.NameU}
    }
    elseif($n.kind -eq 'ellipse'){$s=$page.DrawOval($x,$y-$h,$x+$w,$y)}
    elseif($n.kind -eq 'diamond'){
      $points=[double[]]@(($x+$w/2),$y,($x+$w),($y-$h/2),($x+$w/2),($y-$h),$x,($y-$h/2),($x+$w/2),$y)
      $s=$page.DrawPolyline($points,0)
    } else {$s=$page.DrawRectangle($x,$y-$h,$x+$w,$y)}
    if(-not $master){$sources[[string]$n.id]=@{type='self-drawn'}}
    Style-Shape $s $n
    $s.NameU='node_'+$n.id
    $map[[string]$n.id]=$s; $expected[$s.NameU]=[string]$n.text
  }
  if($spec.page.title){
    $s=$page.DrawRectangle(0.3,$height-0.55,$width-0.3,$height-0.1)
    Style-Shape $s ([pscustomobject]@{kind='text';text=$spec.page.title;fontSize=16;bold=$true})
    $s.NameU='diagram_title'; $expected[$s.NameU]=[string]$spec.page.title
  }
  $edgeIndex=0
  foreach($e in $spec.edges){
    $edgeIndex++
    if($e.routePoints){
      $coords=[Collections.Generic.List[double]]::new()
      foreach($p in $e.routePoints){$coords.Add([double]$p[0]);$coords.Add($height-[double]$p[1])}
      $s=$page.DrawPolyline([double[]]$coords.ToArray(),8)
      if(-not $s.OneD){throw 'Routed polyline is not a 1D connector'}
      $s.DeleteSection(10);$s.AddSection(10) | Out-Null
      $s.AddRow(10,0,137) | Out-Null
      $vertex=0
      foreach($p in $e.routePoints){
        $lx=0.0;$ly=0.0;$s.XYFromPage([double]$p[0],($height-[double]$p[1]),[ref]$lx,[ref]$ly)
        $tag=if($vertex -eq 0){138}else{139}
        $row=$s.AddRow(10,-1,$tag)
        $s.CellsSRC(10,$row,0).ResultIU=$lx;$s.CellsSRC(10,$row,1).ResultIU=$ly;$vertex++
      }
      Set-Cell $s 'Geometry1.NoFill' 'TRUE'
    }else{$s=$page.Drop($app.ConnectorToolDataObject,0,0)}
    $s.NameU="edge_$edgeIndex"
    Glue-Port $s.CellsU('BeginX') $map[[string]$e.from] $e.fromPort $e.fromFraction
    Glue-Port $s.CellsU('EndX') $map[[string]$e.to] $e.toPort $e.toFraction
    Set-Cell $s 'EndArrow' '4';Set-Cell $s 'BeginArrow' '0'
    Set-Cell $s 'LineColor' 'RGB(64,64,64)';Set-Cell $s 'LineWeight' '0.75 pt'
    Set-Cell $s 'Char.Font' 'FONT("Microsoft YaHei")';Set-Cell $s 'Char.Size' '10 pt'
    Set-Cell $s 'Char.AsianFont' 'FONT("Microsoft YaHei")'
    if($e.routePoints){Set-Cell $s 'TxtAngle' '-Angle'}
    if($e.dashed){Set-Cell $s 'LinePattern' '2'}
    if($e.label){
      $expected[$s.NameU]=''
      $l=$e.label
      $label=$page.DrawRectangle($l.x,$height-$l.y-$l.h,$l.x+$l.w,$height-$l.y)
      Style-Shape $label ([pscustomobject]@{kind='text';text=$e.text;fontSize=10})
      $label.NameU="edge_label_$edgeIndex"; $expected[$label.NameU]=[string]$e.text
    } else {$s.Text=[string]$e.text; $expected[$s.NameU]=[string]$e.text}
  }
  $doc.SaveAs($out)
  $page.Export($png)
  $doc.Close();$doc=$null
  $verified=$app.Documents.OpenEx($out,2)
  $vp=$verified.Pages.Item(1)
  if($vp.Shapes.Count -ne $expected.Count){throw 'Reopened shape count mismatch'}
  foreach($key in $expected.Keys){
    $actual=([string]$vp.Shapes.ItemU($key).Text).Replace("`r`n","`n").TrimEnd("`r","`n")
    if($actual -cne $expected[$key].Replace("`r`n","`n").TrimEnd("`r","`n")){throw "Reopened text mismatch: $key"}
  }
  if($vp.Connects.Count -ne 2*$edgeIndex){throw "Expected $($edgeIndex*2) glued endpoints, found $($vp.Connects.Count)"}
  foreach($id in $sources.Keys){if($sources[$id].type -eq 'stencil' -and $vp.Shapes.ItemU('node_'+$id).Master.NameU -ne $sources[$id].master){throw 'Reopened master mismatch'}}
  $index=0;$routePointsChecked=0
  foreach($e in $spec.edges){$index++;if(-not $e.routePoints){continue};$line=$vp.Shapes.ItemU("edge_$index")
    if($line.RowCount(10) -ne @($e.routePoints).Count+1){throw 'Saved route vertex count mismatch'}
    for($j=0;$j -lt @($e.routePoints).Count;$j++){
      $lx=$line.CellsSRC(10,($j+1),0).ResultIU;$ly=$line.CellsSRC(10,($j+1),1).ResultIU
      $px=0.0;$py=0.0;$line.XYToPage($lx,$ly,[ref]$px,[ref]$py)
      if([Math]::Abs($px-$e.routePoints[$j][0]) -gt .001 -or [Math]::Abs($py-($height-$e.routePoints[$j][1])) -gt .001){throw 'Saved route position mismatch'};$routePointsChecked++
    }
  }
  [ordered]@{status=$(if($spec._localLayout.status -eq 'DEGRADED'){'DEGRADED'}else{'PASS'});nativeVerification='PASS';visualReview='REQUIRED';unresolvedIssues=@($warnings)+@($(if($spec._localLayout.status -eq 'DEGRADED'){$spec._localLayout.reason}));visioVersion=$app.Version;nodes=@($spec.nodes).Count;edges=$edgeIndex;reopenedShapes=$vp.Shapes.Count;gluedEndpoints=$vp.Connects.Count;shapeSources=$sources;routing=$spec._routingValidation;layoutOptimization=$spec._layoutOptimization;localLayout=$spec._localLayout;savedRoutePointsChecked=$routePointsChecked;warnings=@($warnings);scope='Reopen, shape count, text, masters, saved planned vertices; routing scope is recorded in routing.scope'} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $report -Encoding utf8
  Write-Output "Created: $out"
  Write-Output "Preview: $png"
  Write-Output "Validation: $report"
} finally {
  if($verified){$verified.Close()}
  if($doc){$doc.Saved=$true;$doc.Close()}
  if($stencil){$stencil.Close()}
  if($app){$app.Quit()}
}
