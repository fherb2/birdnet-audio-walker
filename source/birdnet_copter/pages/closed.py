"""
Closed page – shown to all connected clients when birdnet-copter shuts down.
Redirects to landing page if the application is running again.
"""

from nicegui import ui, app as nicegui_app


@ui.page('/closed')
async def closed_page() -> None:
    ui.page_title('birdnet-copter – closed')
    ui.add_head_html('<link rel="icon" href="data:,">')

    # If the app is still/again running, redirect to landing page
    try:
        shutting_down = nicegui_app.state.bundle.shared_state.get(
            'app_shutting_down', False
        )
        if not shutting_down:
            ui.navigate.to('/')
            return
    except Exception:
        pass

    with ui.column().classes('items-center justify-center w-full q-mt-xl gap-4'):
        ui.label('birdnet-copter has been shut down.').classes('text-h5')
        ui.label('You can close this browser tab or wait until the server is running again.').classes('text-body1 text-grey-7')