import click

from app.extensions import db


def register_cli(flask_app):
    @flask_app.cli.command('seed')
    def seed_command():
        """Create all tables and insert seed data."""
        from app.migrations import create_last_updated_triggers
        db.create_all()
        create_last_updated_triggers(db)
        from app.seed import seed
        seed(db)
        click.echo('Database seeded.')

    @flask_app.cli.command('import-jpop')
    def import_jpop_command():
        """Import JPOP data from 'lettuce jpop.xlsx'."""
        from scripts.import_jpop_data import import_jpop
        import_jpop()
        click.echo('JPOP import complete.')

    @flask_app.cli.command('import-rock')
    def import_rock_command():
        """Import data from 'lettuce billy joel.xlsx'."""
        from scripts.import_rock_data import import_rock
        import_rock()
        click.echo('Rock import complete.')

    @flask_app.cli.command('fetch-album-dates')
    def fetch_album_dates_command():
        """Fetch exact release dates for albums from MusicBrainz."""
        from scripts.fetch_album_dates import fetch_album_dates
        fetch_album_dates()
        click.echo('Album date fetch complete.')

    @flask_app.cli.command('export-spreadsheet')
    def export_spreadsheet_command():
        """Export data to spreadsheet format."""
        from scripts.export_spreadsheet import export_spreadsheet
        export_spreadsheet()
        click.echo('Export complete.')
