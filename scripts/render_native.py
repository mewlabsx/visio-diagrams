"""Plan and write editable VSDX without starting Visio. Structural evidence only."""
import argparse
import copy
import hashlib
import json
import shutil
import posixpath
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from vsdx_writer import STENCIL, write_vsdx


def check_package(path, spec):
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        if package.testzip() is not None:
            raise ValueError('ZIP integrity failure')
        parts = set(names)
        for name in names:
            if not name.endswith(('.xml', '.rels')):
                continue
            root = ET.fromstring(package.read(name))
            if name.endswith('.rels'):
                folder = '' if name == '_rels/.rels' else posixpath.dirname(posixpath.dirname(name))
                for rel in root:
                    if rel.get('TargetMode') == 'External':
                        raise ValueError('External package relationship is unsupported')
                    target = rel.get('Target', '')
                    resolved = posixpath.normpath(posixpath.join(folder, target))
                    if resolved not in parts:
                        raise ValueError('Unresolved relationship: ' + resolved)
        ns = {'v': 'http://schemas.microsoft.com/office/visio/2012/main'}
        page = ET.fromstring(package.read('visio/pages/page1.xml'))
        shapes = page.findall('v:Shapes/v:Shape', ns)
        connects = page.findall('v:Connects/v:Connect', ns)
        expected = len(spec['nodes']) + len(spec['edges']) + bool(spec['page'].get('title'))
        expected += sum(bool(e.get('label') and e.get('text')) for e in spec['edges'])
        if len(shapes) != expected or len(connects) != 2 * len(spec['edges']):
            raise ValueError('Shape or glue count mismatch')
        return {'status': 'PASS', 'shapeCount': len(shapes), 'gluedEndpoints': len(connects),
                'scope': 'ZIP integrity, XML syntax, relationship targets and object counts; not Visio acceptance'}


def render(spec, output, color_fill='spec', stencil=None):
    output = Path(output).resolve()
    if output.suffix.lower() != '.vsdx':
        raise ValueError('Output must end in .vsdx')
    planned_path = output.with_suffix('.planned.json')
    report_path = output.with_suffix('.validation.json')
    for path in (output, planned_path, report_path):
        if path.exists():
            raise FileExistsError('Refusing to overwrite: ' + str(path))
    work = copy.deepcopy(spec)
    use_color = work['page'].get('colorFill', True)
    if not isinstance(use_color, bool):
        raise ValueError('page.colorFill must be boolean')
    if color_fill != 'spec':
        use_color = color_fill == 'on'
    if not use_color:
        for node in work['nodes']:
            node['fill'] = '#FFFFFF'
    if work.get('localLayout'):
        from local_layout import solve
        work = solve(work)
    elif any(e.get('routeGroup') for e in work['edges']):
        from plan_routes import plan
        work = plan(work)
    stencil = stencil or STENCIL
    output.parent.mkdir(parents=True, exist_ok=True)
    # Build and inspect privately; failed input cannot leave a partial target.
    with tempfile.TemporaryDirectory(prefix='vsdx-build-', dir=output.parent) as temp:
        temp = Path(temp)
        drawing = temp/'drawing.vsdx'
        masters = write_vsdx(work, drawing, stencil)
        structure = check_package(drawing, work)
        report = {
            'status': 'GENERATED', 'backend': 'python', 'structure': structure,
            'visioAcceptance': 'NOT_RUN', 'visualReview': 'NOT_RUN', 'png': None,
            'masters': masters, 'stencil': str(Path(stencil).resolve()),
            'sha256': hashlib.sha256(drawing.read_bytes()).hexdigest(),
            'layout': work.get('_localLayout'), 'routing': work.get('_routingValidation'),
            'unplannedEdges': sum(not e.get('routePoints') for e in work['edges']),
        }
        plan_file, report_file = temp/'planned.json', temp/'validation.json'
        plan_file.write_text(json.dumps(work, ensure_ascii=False, indent=2), encoding='utf-8')
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        published = []
        try:
            # Exclusive creation also works on filesystems/sandboxes without hard links.
            for source, target in ((plan_file, planned_path), (report_file, report_path), (drawing, output)):
                with target.open('xb') as dest:
                    published.append(target)
                    with source.open('rb') as src:
                        shutil.copyfileobj(src, dest)
        except OSError:
            for target in published:
                target.unlink()
            raise
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('output')
    parser.add_argument('--color-fill', choices=('spec', 'on', 'off'), default='spec')
    parser.add_argument('--stencil', help='Basic flowchart VSSX resource; no Office process required')
    args = parser.parse_args()
    try:
        result = render(json.loads(Path(args.input).read_text(encoding='utf-8-sig')),
                        args.output, args.color_fill, args.stencil)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile, ET.ParseError) as error:
        raise SystemExit(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
