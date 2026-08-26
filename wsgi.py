from app import create_app

app = create_app()

# Run in production with:
#   waitress-serve --host=0.0.0.0 --port=8080 --call wsgi:app
# (Note: since app is already the created instance here, NOT a factory,
#  drop --call and just use:  waitress-serve --host=0.0.0.0 --port=8080 wsgi:app )