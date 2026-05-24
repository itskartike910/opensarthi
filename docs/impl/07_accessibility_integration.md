# OpenSarthi — Implementation Plan
## Part 7: Accessibility Integration (AT-SPI)

> **Priority:** P1 — Desktop Understanding. After P0 execution engine.
> **Affected files:** `runtime/observation.py` [UPDATE], `runtime/providers/linux/accessibility.py` [NEW]

---

## 1. Why AT-SPI First (Not Screenshots)

Screenshots + OCR is an unreliable last resort. AT-SPI gives you:

| Capability | AT-SPI | Screenshot+OCR |
|-----------|--------|----------------|
| Button text | ✅ Exact | ⚠ Sometimes inaccurate |
| Element role | ✅ (button, input, link) | ❌ Cannot determine |
| Element state | ✅ (focused, disabled, checked) | ❌ Cannot determine |
| Click target precision | ✅ Center of bounding box | ⚠ Approximate |
| Input field detection | ✅ Reliable | ⚠ Unreliable |
| Performance | ✅ <10ms per query | ❌ 200-800ms (OCR) |
| Works without display | ✅ | ❌ |

AT-SPI is already used by screen readers (Orca), automation tools (LDTP), and KDE's accessibility system. It's the **correct** primary source of UI truth on Linux.

---

## 2. AT-SPI Architecture

```
KDE/GTK App → AT-SPI D-Bus → PyGObject (gi.Atspi) → OpenSarthi
```

**Requires:**
- `at-spi2-core` (system package, likely already installed on KDE)
- `PyGObject>=3.50` (already in requirements.txt)
- `python-gi` (included with PyGObject)

**Check if AT-SPI is running:**
```bash
systemctl --user status at-spi-dbus-bus.service
# or
ps aux | grep at-spi
```

---

## 3. AccessibilityProvider (`runtime/providers/linux/accessibility.py`)

```python
"""
AT-SPI 2.0 Accessibility Provider for OpenSarthi.

Uses GObject Introspection to access the AT-SPI D-Bus tree.
This gives us: element roles, text, states, bounding boxes.

Requires: python-gi (PyGObject) + at-spi2-core
"""

import asyncio
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class UIElement:
    """A single accessible UI element."""
    role: str                          # "button", "text", "entry", "menu-item", ...
    name: str                          # Display name/label
    description: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    is_focused: bool = False
    is_enabled: bool = True
    is_visible: bool = True
    children: List["UIElement"] = None

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def __repr__(self):
        return f"UIElement(role={self.role!r}, name={self.name!r}, at=({self.x},{self.y}))"


class AccessibilityProvider:
    """
    Walks the AT-SPI accessibility tree to find UI elements.
    
    Usage:
        provider = AccessibilityProvider()
        elements = provider.find_elements(role="button")
        focused = provider.get_focused_element()
    """

    def __init__(self):
        self._available = False
        self._desktop = None
        self._load()

    def _load(self):
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            self._Atspi = Atspi
            self._desktop = Atspi.get_desktop(0)
            self._available = True
            print("[AT-SPI] Accessibility provider loaded")
        except Exception as e:
            print(f"[AT-SPI] Not available: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def get_focused_element(self) -> Optional[UIElement]:
        """Return the currently focused UI element."""
        if not self._available:
            return None
        try:
            Atspi = self._Atspi
            focused = None

            def walk(obj, depth=0):
                nonlocal focused
                if depth > 20:
                    return
                try:
                    state_set = obj.get_state_set()
                    if state_set.contains(Atspi.StateType.FOCUSED):
                        focused = self._to_element(obj)
                        return
                    n = obj.get_child_count()
                    for i in range(min(n, 50)):  # Cap tree walk
                        child = obj.get_child_at_index(i)
                        if child:
                            walk(child, depth + 1)
                except Exception:
                    pass

            for i in range(self._desktop.get_child_count()):
                app = self._desktop.get_child_at_index(i)
                if app:
                    walk(app)
                if focused:
                    break

            return focused
        except Exception:
            return None

    def find_elements(
        self,
        role: Optional[str] = None,
        name: Optional[str] = None,
        name_contains: Optional[str] = None,
        max_results: int = 20
    ) -> List[UIElement]:
        """
        Search the accessibility tree for elements matching criteria.
        
        Examples:
            # Find all buttons
            buttons = provider.find_elements(role="button")
            
            # Find a specific button by name
            submit = provider.find_elements(role="button", name="Submit")
            
            # Find any element containing text
            elements = provider.find_elements(name_contains="Login")
        """
        if not self._available:
            return []

        results = []

        def walk(obj, depth=0):
            if len(results) >= max_results or depth > 15:
                return
            try:
                el = self._to_element(obj)
                matches = True
                if role and el.role != role:
                    matches = False
                if name and el.name != name:
                    matches = False
                if name_contains and name_contains.lower() not in el.name.lower():
                    matches = False

                if matches and el.name:
                    results.append(el)

                for i in range(min(obj.get_child_count(), 100)):
                    child = obj.get_child_at_index(i)
                    if child:
                        walk(child, depth + 1)
            except Exception:
                pass

        try:
            for i in range(self._desktop.get_child_count()):
                app = self._desktop.get_child_at_index(i)
                if app:
                    walk(app)
        except Exception:
            pass

        return results

    def get_active_window(self) -> Optional[UIElement]:
        """Return the currently active application window."""
        if not self._available:
            return None

        try:
            Atspi = self._Atspi
            for i in range(self._desktop.get_child_count()):
                app = self._desktop.get_child_at_index(i)
                if not app:
                    continue
                for j in range(app.get_child_count()):
                    win = app.get_child_at_index(j)
                    if not win:
                        continue
                    try:
                        states = win.get_state_set()
                        if states.contains(Atspi.StateType.ACTIVE):
                            return self._to_element(win)
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def click_element(self, element: UIElement) -> bool:
        """Click the center of an element using its bounding box."""
        import subprocess
        cx, cy = element.center
        result = subprocess.run(
            ["xdotool", "mousemove", str(cx), str(cy), "click", "1"],
            capture_output=True
        )
        return result.returncode == 0

    def get_tree_summary(self, max_elements: int = 50) -> str:
        """Return a text summary of visible UI elements for the LLM prompt."""
        elements = self.find_elements(max_results=max_elements)
        if not elements:
            return "No accessible UI elements found."

        lines = [f"Accessible UI Elements ({len(elements)}):"]
        for el in elements:
            state = "FOCUSED" if el.is_focused else ""
            lines.append(f"  [{el.role}] '{el.name}' at ({el.x},{el.y}) {state}".rstrip())
        return "\n".join(lines)

    def _to_element(self, obj) -> UIElement:
        """Convert an Atspi.Accessible object to UIElement."""
        Atspi = self._Atspi
        try:
            role = obj.get_role_name() or "unknown"
            name = obj.get_name() or ""
            description = obj.get_description() or ""

            # Get bounding box
            try:
                bbox = obj.get_extents(Atspi.CoordType.SCREEN)
                x, y, w, h = bbox.x, bbox.y, bbox.width, bbox.height
            except Exception:
                x = y = w = h = 0

            # Check states
            try:
                states = obj.get_state_set()
                is_focused = states.contains(Atspi.StateType.FOCUSED)
                is_enabled = states.contains(Atspi.StateType.ENABLED)
                is_visible = states.contains(Atspi.StateType.VISIBLE)
            except Exception:
                is_focused = is_enabled = is_visible = True

            return UIElement(
                role=role, name=name, description=description,
                x=x, y=y, width=w, height=h,
                is_focused=is_focused, is_enabled=is_enabled, is_visible=is_visible
            )
        except Exception:
            return UIElement(role="unknown", name="")
```

---

## 4. Integrating Into DesktopObserver

**Update `runtime/observation.py`:**

```python
from providers.linux.accessibility import AccessibilityProvider

class DesktopObserver:
    def __init__(self):
        self._display = self._detect_display()
        self._a11y = AccessibilityProvider()  # Add this

    async def snapshot(self) -> DesktopSnapshot:
        snap = DesktopSnapshot()

        # 1. Active window
        snap.active_window_title = await self._get_active_window_title()

        # 2. AT-SPI focused element (primary — fast)
        if self._a11y.available:
            focused = self._a11y.get_focused_element()
            if focused:
                snap.focused_element_role = focused.role
                snap.focused_element_text = focused.name
            # Include UI tree summary for LLM
            snap.accessibility_tree = {
                "summary": self._a11y.get_tree_summary(max_elements=30)
            }

        # 3. OCR fallback (only if AT-SPI gave us nothing useful)
        if not snap.focused_element_text:
            snap.screen_text_summary = await self._ocr_active_region()

        return snap
```

---

## 5. State-Aware Click Using AT-SPI

**New tool: `click_element` (semantic click)**

```python
# tools/desktop.py — new tool

class ClickElementTool(BaseTool):
    name = "click_element"
    description = (
        "Click a UI element by its role and name using AT-SPI. "
        "More reliable than coordinate clicking. "
        "Args: role (string), name (string)"
    )
    risk_level = RiskLevel.MODERATE

    async def execute(self, args: dict) -> ToolResult:
        from providers.linux.accessibility import AccessibilityProvider
        role = args.get("role", "")
        name = args.get("name", "")

        if not role and not name:
            return ToolResult.fail("Provide at least one of: role, name", retryable=False)

        provider = AccessibilityProvider()
        if not provider.available:
            return ToolResult.fail(
                "AT-SPI not available — use coordinate click instead",
                retryable=False
            )

        elements = provider.find_elements(
            role=role or None,
            name=name or None,
            name_contains=name or None,
            max_results=5
        )

        if not elements:
            return ToolResult.fail(
                f"No element found: role={role!r} name={name!r}",
                retryable=True,
                suggested_next="Try a coordinate click or check element names with observe_desktop"
            )

        target = elements[0]
        success = provider.click_element(target)

        if success:
            return ToolResult.ok(
                observation=f"Clicked [{target.role}] '{target.name}' at {target.center}",
                confidence=ToolResultConfidence.HIGH,
                ui_changed=True
            )
        else:
            return ToolResult.fail("xdotool click failed", retryable=True)
```

---

## 6. Implementation Checklist

- [ ] Check AT-SPI is running: `systemctl --user status at-spi-dbus-bus.service`
- [ ] Verify PyGObject import: `python -c "import gi; gi.require_version('Atspi','2.0'); from gi.repository import Atspi; print(Atspi.get_desktop(0))"`
- [ ] Create `runtime/providers/linux/accessibility.py`
- [ ] Test `AccessibilityProvider.get_focused_element()` with Konsole focused
- [ ] Test `AccessibilityProvider.find_elements(role="button")` with a GUI app open
- [ ] Update `observation.py` to use `AccessibilityProvider` in `snapshot()`
- [ ] Add `ClickElementTool` to tool registry
- [ ] Test end-to-end: "click the Submit button" → AT-SPI finds it → xdotool click

---

## 7. Known Limitations

| App | AT-SPI Support | Notes |
|-----|---------------|-------|
| KDE/Qt apps | ✅ Good | Most KDE apps expose full tree |
| GTK apps | ✅ Good | Firefox, GNOME apps |
| Electron apps | ⚠ Partial | Chromium AT-SPI support is limited |
| Wayland-native | ⚠ Partial | Some compositors block AT-SPI |
| Games / OpenGL | ❌ None | Use screenshot + OCR |

For apps without AT-SPI, fall through to coordinate clicking via screenshot OCR.

---

> Next: [08_prompting_architecture.md](./08_prompting_architecture.md)
