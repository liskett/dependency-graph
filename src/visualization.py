"""Export a dependency graph as Mermaid text and a standalone SVG image."""

from collections import deque
from html import escape
from pathlib import Path
from xml.etree import ElementTree as element_tree

from src.cargo import DependencyError


MARGIN = 50
MIN_NODE_WIDTH = 190
NODE_HEIGHT = 44
CHAR_WIDTH = 9
LABEL_PADDING = 32
COLUMN_GAP = 100
ROW_GAP = 78
CURVE_OFFSET = 60
HALF = 2


def _graph_depths(
    graph: dict[str, list[str]], root: str
) -> dict[str, int]:
    """Find BFS depths and reject missing nodes or dangling edges."""
    if root not in graph:
        raise DependencyError(f"Root package '{root}' is missing in graph.")
    for dependencies in graph.values():
        for target in dependencies:
            if target not in graph:
                raise DependencyError(
                    f"Graph references missing dependency '{target}'."
                )
    depths = {root: 0}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for target in sorted(graph[node]):
            if target not in depths:
                depths[target] = depths[node] + 1
                queue.append(target)
    for node in graph:
        depths.setdefault(node, 0)
    return depths


def to_mermaid(graph: dict[str, list[str]], root: str) -> str:
    """Create Mermaid flowchart text with a node for each package version."""
    _graph_depths(graph, root)
    ids = {name: f"n{index}" for index, name in enumerate(sorted(graph))}
    lines = ["flowchart LR"]
    for name, identifier in ids.items():
        lines.append(f'    {identifier}["{escape(name, quote=True)}"]')
    for source in sorted(graph):
        for target in sorted(set(graph[source])):
            lines.append(f"    {ids[source]} --> {ids[target]}")
    return "\n".join(lines)


def _node_layout(
    depths: dict[str, int], node_width: int
) -> tuple[dict[str, tuple[int, int]], int, int]:
    """Place package nodes into columns according to BFS depth."""
    layers: dict[int, list[str]] = {}
    for name in sorted(depths):
        layers.setdefault(depths[name], []).append(name)
    positions = {}
    for level, names in layers.items():
        for row, name in enumerate(names):
            x_pos = MARGIN + level * (node_width + COLUMN_GAP)
            y_pos = MARGIN + row * ROW_GAP
            positions[name] = (x_pos, y_pos)
    width = MARGIN * HALF + node_width
    width += max(layers) * (node_width + COLUMN_GAP)
    height = MARGIN * HALF + NODE_HEIGHT
    height += (max(map(len, layers.values())) - 1) * ROW_GAP
    return positions, width, height


def _edge_path(
    source: tuple[int, int], target: tuple[int, int],
    node_width: int, lane_y: int,
) -> str:
    """Route forward, same-level, and returning dependency arrows."""
    sx, sy = source
    tx, ty = target
    middle = NODE_HEIGHT // HALF
    if source == target:
        right = sx + node_width
        return (
            f"M {right} {sy + 10} "
            f"C {right + CURVE_OFFSET} {sy - 20}, "
            f"{right + CURVE_OFFSET} {sy + NODE_HEIGHT + 20}, "
            f"{right} {sy + NODE_HEIGHT - 10}"
        )
    if sx < tx:
        first, last = sx + node_width, tx
        return (
            f"M {first} {sy + middle} "
            f"C {first + CURVE_OFFSET} {sy + middle}, "
            f"{last - CURVE_OFFSET} {ty + middle}, {last} {ty + middle}"
        )
    center = sx + node_width // HALF
    if sx == tx:
        if sy > ty:
            return f"M {center} {sy} L {center} {ty + NODE_HEIGHT}"
        return f"M {center} {sy + NODE_HEIGHT} L {center} {ty}"
    target_center = tx + node_width // HALF
    return (
        f"M {center} {sy + NODE_HEIGHT} "
        f"L {center} {lane_y} L {target_center} {lane_y} "
        f"L {target_center} {ty + NODE_HEIGHT}"
    )


def _svg_edges(
    parent: element_tree.Element,
    graph: dict[str, list[str]],
    positions: dict[str, tuple[int, int]],
    node_width: int,
    lane_y: int,
) -> None:
    """Render each unique dependency edge as an SVG arrow."""
    for source in sorted(graph):
        for target in sorted(set(graph[source])):
            element_tree.SubElement(parent, "path", {
                "d": _edge_path(
                    positions[source], positions[target], node_width, lane_y
                ),
                "fill": "none", "stroke": "#64748b", "stroke-width": "2",
                "marker-end": "url(#arrow)",
            })


def _svg_nodes(
    parent: element_tree.Element,
    positions: dict[str, tuple[int, int]],
    root: str,
    node_width: int,
) -> None:
    """Draw labeled rectangles, highlighting the graph's root package."""
    for name, (x_pos, y_pos) in sorted(positions.items()):
        element_tree.SubElement(parent, "rect", {
            "x": str(x_pos), "y": str(y_pos),
            "width": str(node_width), "height": str(NODE_HEIGHT),
            "rx": "8", "stroke": "#334155", "stroke-width": "1.5",
            "fill": "#dcfce7" if name == root else "#f8fafc",
        })
        label = element_tree.SubElement(parent, "text", {
            "x": str(x_pos + node_width // HALF),
            "y": str(y_pos + NODE_HEIGHT // HALF),
            "text-anchor": "middle", "dominant-baseline": "central",
            "font-family": "monospace", "font-size": "13",
            "fill": "#0f172a",
        })
        label.text = name


def to_svg(graph: dict[str, list[str]], root: str) -> str:
    """Render a portable SVG with the same nodes and edges as Mermaid."""
    depths = _graph_depths(graph, root)
    node_width = max(
        MIN_NODE_WIDTH, max(map(len, graph)) * CHAR_WIDTH + LABEL_PADDING
    )
    positions, width, height = _node_layout(depths, node_width)
    lane_y = height + ROW_GAP // HALF
    has_return = any(
        positions[src][0] > positions[dst][0]
        for src in graph for dst in graph[src]
    )
    if has_return:
        height += ROW_GAP
    width += CURVE_OFFSET
    svg = element_tree.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": str(width), "height": str(height),
        "viewBox": f"0 0 {width} {height}",
    })
    element_tree.SubElement(svg, "title").text = f"Dependencies of {root}"
    definitions = element_tree.SubElement(svg, "defs")
    marker = element_tree.SubElement(definitions, "marker", {
        "id": "arrow", "markerWidth": "8", "markerHeight": "8",
        "refX": "7", "refY": "4", "orient": "auto",
    })
    element_tree.SubElement(marker, "path", {
        "d": "M 0 0 L 8 4 L 0 8 z", "fill": "#64748b"
    })
    _svg_edges(element_tree.SubElement(svg, "g", {"id": "edges"}),
               graph, positions, node_width, lane_y)
    _svg_nodes(element_tree.SubElement(svg, "g", {"id": "nodes"}),
               positions, root, node_width)
    return element_tree.tostring(svg, encoding="unicode")


def save_visualization(
    graph: dict[str, list[str]], root: str, output: str
) -> str:
    """Save matching Mermaid and SVG files, reporting filesystem errors."""
    target = Path(output)
    if target.suffix.lower() != ".svg":
        raise DependencyError("Visualization output must be an SVG file.")
    mermaid = to_mermaid(graph, root)
    svg = to_svg(graph, root)
    try:
        target.with_suffix(".mmd").write_text(mermaid + "\n", encoding="utf-8")
        target.write_text(svg + "\n", encoding="utf-8")
    except OSError as error:
        message = f"Could not save visualization: {error}."
        raise DependencyError(message) from error
    return mermaid