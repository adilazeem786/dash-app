from dash import Dash

app = Dash(__name__)
server = app.server

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8050))
    app.run_server(debug=True, port=port)
