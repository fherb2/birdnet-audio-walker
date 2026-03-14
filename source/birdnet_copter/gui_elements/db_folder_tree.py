"""
DbFolderTree – checkbox tree widget for selecting folders that contain
a birdnet_analysis.db SQLite database.

Only folders that contain a DB somewhere in their subtree are shown.
Folders without any DB in their subtree are pruned completely.

Visual structure (CSS border-left lines, no monospace art):
  root_path/
    ▼ 2024/                     ← group header (no DB itself), group checkbox
        ☑ Mai_Wald/             ← has DB, selectable
        ☑ Juni_Wiese/           ← has DB, selectable
    ☑ ▶ Test_2023/              ← has DB itself AND children with DB

Usage:
    tree = DbFolderTree(
        root_path=state.root_path,
        on_change=lambda folders: ...,   # called with Set[Path] on every change
    )
    # Read current selection:
    paths: set[Path] = tree.selected_folders
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Set

from nicegui import ui

# Filename of the SQLite database we look for
DB_FILENAME = 'birdnet_analysis.db'


# ---------------------------------------------------------------------------
# Tree data model
# ---------------------------------------------------------------------------

@dataclass
class DbFolderTreeNode:
    """
    One node in the scanned folder tree.

    Attributes:
        path:     Absolute path of this folder.
        has_db:   True if this folder directly contains birdnet_analysis.db.
        children: Child nodes that themselves have a DB or have children with DBs.
                  Sorted by folder name.
    """
    path: Path
    has_db: bool
    children: list['DbFolderTreeNode'] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_leaf(self) -> bool:
        """True if this node has no relevant children."""
        return len(self.children) == 0

    @property
    def is_group_only(self) -> bool:
        """True if node has no DB itself but has children (pure group header)."""
        return not self.has_db and len(self.children) > 0


# ---------------------------------------------------------------------------
# Recursive tree scan  (runs in executor – blocking I/O)
# ---------------------------------------------------------------------------

def _scan_node(folder: Path) -> Optional[DbFolderTreeNode]:
    """
    Recursively scan *folder* and return a DbFolderTreeNode if the folder
    or any descendant contains a DB.  Returns None if the subtree has no DB.

    Skips hidden folders (starting with '.').
    """
    try:
        entries = sorted(
            p for p in folder.iterdir()
            if p.is_dir() and not p.name.startswith('.')
        )
    except PermissionError:
        return None

    has_db = (folder / DB_FILENAME).exists()

    children: list[DbFolderTreeNode] = []
    for entry in entries:
        child = _scan_node(entry)
        if child is not None:
            children.append(child)

    # Prune: only keep this node if it has a DB or relevant children
    if not has_db and not children:
        return None

    return DbFolderTreeNode(path=folder, has_db=has_db, children=children)


# ---------------------------------------------------------------------------
# DbFolderTree widget
# ---------------------------------------------------------------------------

class DbFolderTree:
    """
    Checkbox tree that lists all folders containing birdnet_analysis.db.

    Args:
        root_path:  Scan starts here; root itself is never shown as a selectable
                    row – its children form the top level.
        on_change:  Called with the current Set[Path] of selected folders
                    whenever the selection changes.
    """

    def __init__(
        self,
        root_path: Path,
        on_change: Optional[Callable[[Set[Path]], None]] = None,
    ) -> None:
        self._root_path = root_path
        self._on_change = on_change

        # Checked state: path → bool
        self._checked: dict[Path, bool] = {}

        # Expand state: path → bool  (True = expanded)
        self._expanded: dict[Path, bool] = {}

        # NiceGUI checkbox widgets: path → ui.checkbox
        self._checkboxes: dict[Path, ui.checkbox] = {}

        # Scanned tree root (set after async scan)
        self._tree_root: Optional[DbFolderTreeNode] = None

        # Outer container
        self._container = ui.column().classes('w-full gap-0')

        # Start async scan + render
        asyncio.create_task(self._scan_and_render())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def selected_folders(self) -> Set[Path]:
        """Return set of currently checked folder paths (that have a DB)."""
        return {p for p, checked in self._checked.items() if checked}

    # ------------------------------------------------------------------
    # Async scan + initial render
    # ------------------------------------------------------------------

    async def _scan_and_render(self) -> None:
        """Scan the folder tree in a thread, then render the result."""
        loop = asyncio.get_event_loop()

        # Show spinner while scanning
        self._container.clear()
        with self._container:
            with ui.row().classes('items-center gap-2 px-2 py-2'):
                ui.spinner(size='sm')
                ui.label('Scanning folders…').classes('text-caption text-grey-7')

        # Blocking scan in thread pool
        root_node = await loop.run_in_executor(None, _scan_node, self._root_path)

        # Build initial expand state: top-level children are expanded
        if root_node is not None:
            for child in root_node.children:
                self._expanded[child.path] = True   # first level open
                # deeper levels start collapsed (default False via dict.get)

        self._tree_root = root_node

        # Render
        self._container.clear()
        with self._container:
            if root_node is None or not root_node.children:
                ui.label('No databases found under the configured root path.') \
                    .classes('text-caption text-grey-6 px-2 py-2')
                return

            for i, child in enumerate(root_node.children):
                is_last = (i == len(root_node.children) - 1)
                self._render_node(child, depth=0, is_last=is_last, ancestor_is_last=[])
                
    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_node(
        self,
        node: DbFolderTreeNode,
        depth: int,
        is_last: bool,
        ancestor_is_last: list[bool],
    ) -> None:
        """
        Render one tree node as a NiceGUI row, then recurse into children
        if the node is currently expanded.

        Visual layout per row:
          [indent lines] [expand btn or spacer] [checkbox or spacer] [folder name]

        CSS border-left lines are drawn via nested divs with left-border styling.
        ancestor_is_last: list of bool, one per ancestor level.
                          True  → that ancestor was the last child → no vertical
                                  line continues at that level.
                          False → vertical line continues.
        """
        expanded = self._expanded.get(node.path, False)
        has_children = not node.is_leaf

        # ------------------------------------------------------------------
        # Row
        # ------------------------------------------------------------------
        with ui.row().classes('items-center gap-0 w-full').style('min-height: 28px'):

            # --- Indentation with vertical lines ---
            for lvl, anc_is_last in enumerate(ancestor_is_last):
                if anc_is_last:
                    # Ancestor was last child → gap (no line)
                    ui.element('div').style('width: 20px; flex-shrink: 0;')
                else:
                    # Ancestor has more siblings below → draw vertical line
                    ui.element('div').style(
                        'width: 20px; flex-shrink: 0;'
                        'border-left: 1px solid #bdbdbd;'
                        'height: 28px;'
                    )

            # --- Connector: horizontal stub from vertical line to content ---
            # This is the elbow/tee at the current node's level
            connector_style = (
                'width: 20px; flex-shrink: 0; height: 28px;'
                'border-left: 1px solid #bdbdbd;'
            )
            if depth > 0 or len(ancestor_is_last) > 0:
                # Draw the elbow/tee line
                with ui.element('div').style(connector_style):
                    # Horizontal part of the elbow
                    ui.element('div').style(
                        'width: 20px; height: 14px;'   # top half: vertical only
                        'border-bottom: 1px solid #bdbdbd;'
                        + ('' if not is_last else '')   # bottom half depends on is_last
                    )
            else:
                ui.element('div').style('width: 20px; flex-shrink: 0;')

            # --- Expand / collapse button (only if has children) ---
            if has_children:
                icon = 'expand_more' if expanded else 'chevron_right'
                expand_btn = ui.button(icon=icon) \
                    .props('flat dense round size=xs') \
                    .style('width: 22px; height: 22px; flex-shrink: 0;')
                # Capture node reference for closure
                expand_btn.on('click', lambda _n=node: self._toggle_expand(_n))
            else:
                # Spacer so checkboxes stay aligned
                ui.element('div').style('width: 22px; flex-shrink: 0;')

            # --- Checkbox (only if node has_db) ---
            if node.has_db:
                cb = ui.checkbox(
                    value=self._checked.get(node.path, False),
                    on_change=lambda e, _n=node: self._on_checkbox_change(_n, e.value),
                ).style('flex-shrink: 0;')
                self._checkboxes[node.path] = cb
            else:
                # Group-only node: show a group checkbox (tri-state visual via indeterminate)
                cb = ui.checkbox(
                    value=self._all_children_checked(node),
                    on_change=lambda e, _n=node: self._on_group_checkbox_change(_n, e.value),
                ).style('flex-shrink: 0;')
                self._checkboxes[node.path] = cb

            # --- Folder name label ---
            name_style = 'font-weight: 500;' if node.is_group_only else ''
            color_class = 'text-grey-7' if node.is_group_only else 'text-grey-10'
            ui.label(node.name) \
                .classes(f'text-body2 {color_class}') \
                .style(name_style + ' user-select: none;')

        # ------------------------------------------------------------------
        # Children (rendered only if expanded)
        # ------------------------------------------------------------------
        if has_children and expanded:
            child_ancestor = ancestor_is_last + [is_last]
            for i, child in enumerate(node.children):
                child_is_last = (i == len(node.children) - 1)
                self._render_node(child, depth + 1, child_is_last, child_ancestor)

    # ------------------------------------------------------------------
    # Expand / collapse
    # ------------------------------------------------------------------

    def _toggle_expand(self, node: DbFolderTreeNode) -> None:
        """Toggle expand state of a node and re-render the whole tree."""
        self._expanded[node.path] = not self._expanded.get(node.path, False)
        self._full_rerender()

    def _full_rerender(self) -> None:
        """Re-render the entire widget contents (keeps checked/expanded state)."""
        if self._tree_root is None:
            return
        self._checkboxes.clear()
        self._container.clear()
        with self._container:
            if not self._tree_root.children:
                return
            for i, child in enumerate(self._tree_root.children):
                is_last = (i == len(self._tree_root.children) - 1)
                self._render_node(child, depth=0, is_last=is_last, ancestor_is_last=[])

    # ------------------------------------------------------------------
    # Checkbox logic
    # ------------------------------------------------------------------

    def _on_checkbox_change(self, node: DbFolderTreeNode, checked: bool) -> None:
        """Handle check/uncheck of a single DB-folder node."""
        self._checked[node.path] = checked
        # Update parent group checkboxes up the tree
        self._refresh_group_checkboxes(self._tree_root)
        self._notify_change()

    def _on_group_checkbox_change(self, node: DbFolderTreeNode, checked: bool) -> None:
        """Handle check/uncheck of a group header – cascades to all DB children."""
        self._set_subtree_checked(node, checked)
        self._refresh_group_checkboxes(self._tree_root)
        # Sync individual checkbox widgets
        for path, is_checked in self._checked.items():
            cb = self._checkboxes.get(path)
            if cb is not None:
                cb.set_value(is_checked)
        self._notify_change()

    def _set_subtree_checked(self, node: DbFolderTreeNode, checked: bool) -> None:
        """Recursively set checked state for all DB-bearing nodes in subtree."""
        if node.has_db:
            self._checked[node.path] = checked
        for child in node.children:
            self._set_subtree_checked(child, checked)

    def _all_children_checked(self, node: DbFolderTreeNode) -> bool:
        """Return True if all DB-bearing descendants of node are checked."""
        db_nodes = self._collect_db_nodes(node)
        if not db_nodes:
            return False
        return all(self._checked.get(p, False) for p in db_nodes)

    def _collect_db_nodes(self, node: DbFolderTreeNode) -> list[Path]:
        """Collect paths of all DB-bearing nodes in the subtree (incl. node itself)."""
        result = []
        if node.has_db:
            result.append(node.path)
        for child in node.children:
            result.extend(self._collect_db_nodes(child))
        return result

    def _refresh_group_checkboxes(self, node: Optional[DbFolderTreeNode]) -> None:
        """
        Walk the tree and update group-header checkbox values to reflect
        whether all their DB-children are checked.
        """
        if node is None:
            return
        if node.is_group_only:
            cb = self._checkboxes.get(node.path)
            if cb is not None:
                cb.set_value(self._all_children_checked(node))
        for child in node.children:
            self._refresh_group_checkboxes(child)

    def _notify_change(self) -> None:
        """Call the on_change callback with the current selection."""
        if self._on_change is not None:
            self._on_change(self.selected_folders)