"""Engine for running over a dask cluster."""

import uuid
import os
import asyncio
import tornado
from contextlib import contextmanager
from dask.distributed import Client
from .dask_common import execute
from ..file import make_file_manager


DEFAULT_CLIENT = 'tcp://localhost:8786'

def make_client(url):
    return Client(url, asynchronous=True)

class DaskDistributedEngine:
    """Allow execution over a dask cluster."""

    client = None
    client_url = DEFAULT_CLIENT

    def __init__(self, config=None):
        if config:
            if 'url' in config:
                self.client_url = config['url']

    def add_data(self, filename, content, session):
        session['data-filename'] = filename
        session['data-content'] = content

    def add_processor(self, filename, content, session):
        session['workflow-filename'] = filename
        session['workflow-content'] = content

    def get_client(self):
        """Return a dask.distributed client, connecting if necessary."""

        if not self.client:
            self.client = make_client(self.client_url)
        return self.client

    async def run(self, filename, workflow_module, bucket=None):
        """Start the execution process over the cluster."""

        return await self._run(filename, workflow_module, bucket, self.get_client())

    async def monitor_pipeline(self, session):
        workflow_module = session['workflow-filename']
        filename = session['data-filename']
        content = {
            workflow_module: session['workflow-content'].decode('utf-8'),
            filename: session['data-content'].decode('utf-8'),
        }

        with make_file_manager(content=content) as file_manager:
            result = await self.run(filename, workflow_module)

        return result

    @staticmethod
    async def _run(filename, workflow_module, bucket, client):
        """Start the execution process over the cluster for a given client."""

        result = None

        with make_file_manager(bucket) as file_manager:
            local_file = file_manager.get(filename)

            await client.upload_file(workflow_module)
            module_name = os.path.splitext(os.path.basename(workflow_module))[0]
            result = await client.submit(execute, local_file, module_name)

        return result

    @contextmanager
    def make_session(self):
        """Set up a workflow session.

        This creates a self-contained set of dask constructs representing our operation.
        """

        name = 'doorstep-%s' % str(uuid.uuid4())
        data_name = '%s-data' % name
        processors_name = '%s-processors' % name

        session = {
            'name': name,
            'data': data_name,
            'processors': processors_name
        }

        yield session
