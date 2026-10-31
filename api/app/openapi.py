"""Print the OpenAPI spec, for generating the typed TypeScript client.

python -m app.openapi > ../packages/api-client/openapi.json
"""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=1))
