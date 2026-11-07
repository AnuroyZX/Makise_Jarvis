# Desktop Overlay & Window Management Rules

1. **Never Steal Focus from Fullscreen Applications**:
   - For transparent overlay windows (such as character avatars, HUDs, or companion widgets), do NOT use `alwaysOnTop: "screen-saver"` or repetitive polling calls to `.moveTop()` / `.setAlwaysOnTop(true)`. This kicks users out of fullscreen DirectX/Vulkan games (e.g. Valorant, CS2, Apex).
   - Use `alwaysOnTop: "normal"` or `alwaysOnTop: "floating"` with `{ focusable: false, skipTaskbar: true }`.

2. **Window Dragging without Stealing Focus**:
   - When `focusable: false` is active, native `-webkit-app-region: drag` is disabled or erratic in Chromium.
   - Implement drag using IPC-based cursor tracking (`screen.getCursorScreenPoint()` delta) with rate-limiting (e.g., ~60fps) and explicit safety boundaries (reset on mouse-up, blur, or inactivity timeout).

3. **Click-Through and Interactivity Boundaries**:
   - Transparent avatar regions must forward mouse events when appropriate using `setIgnoreMouseEvents(true, { forward: true })`.
   - Hover and interactive controls must reliably toggle `setIgnoreMouseEvents(false)` only when the pointer is over interactive UI elements.
