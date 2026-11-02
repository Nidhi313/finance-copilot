"""Send request traces, dependencies and logs to Application Insights when running
in Azure. Does nothing locally, where APPLICATIONINSIGHTS_CONNECTION_STRING is unset."""

from app.config import settings


def setup_telemetry() -> bool:
    if not settings.applicationinsights_connection_string:
        return False
    # Imported lazily so local runs and tests never load the exporter.
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=settings.applicationinsights_connection_string)
    return True
