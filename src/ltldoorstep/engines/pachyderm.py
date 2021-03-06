"""Engine for running a job on a Pachyderm cluster."""

from contextlib import contextmanager
import asyncio
import time
import os
import sys
import json
import uuid
import pypachy
from concurrent.futures import ThreadPoolExecutor
from .pachyderm_proxy.repo import make_repo
from .pachyderm_proxy.pipeline import make_pipeline
from .pachyderm_proxy.job_error import JobFailedException
from .pachyderm_proxy.pypachy_wrapper import PfsClientWrapper


class PachydermEngine:
    """Allow execution of workflows on a Pachyderm cluster."""

    _retry_count = 120
    _retry_delay = 1.0
    _retry_processing_count = 50
    pipeline_definition = None

    def __init__(self):
        self.set_clients(
            pps=pypachy.pps_client.PpsClient(),
            pfs=PfsClientWrapper()
        )

        self._pipeline_template = os.path.join(
            os.path.dirname(__file__),
            'pachyderm_proxy',
            'doorstep.json'
        )

    def get_definition(self):
        """Load and set the pipeline definition."""

        if not self.pipeline_definition:
            with open(self._pipeline_template, 'r') as file_obj:
                self.pipeline_definition = json.load(file_obj)

        return self.pipeline_definition

    def get_clients(self):
        """Get the client objects used to communicate with Pachyderm."""

        return (self._clients['pps'], self._clients['pfs'])

    def set_clients(self, pps, pfs):
        """Set the client objects to communicate with Pachyderm."""

        self._clients = {
            'pps': pps,
            'pfs': pfs
        }

    def add_processor(self, module_name, content, session):
        """Mark a module_name as a processor."""

        filename = '/%s.py' % module_name
        self._add_file('processors', filename, content, session)

    def add_data(self, filename, content, session, bucket=None):
        """Prepare to send a data file to Pachyderm."""

        filename = '/%s' % filename
        self._add_file('data', filename, content, session, bucket)

    def _add_file(self, category, filename, content, session, bucket=None):
        """Transfer file to Pachyderm."""

        with session[category].make_commit('master') as commit:
            if bucket:
                commit.put_file_url(
                    filename,
                    's3://%s/%s' % (bucket, content)
                )
            else:
                commit.put_file_bytes(
                    filename,
                    content
                )

    @contextmanager
    def make_session(self):
        """Set up a workflow session.

        This creates a self-contained set of Pachyderm constructs representing our operation.
        """

        clients = self._clients

        name = 'doorstep-%s' % str(uuid.uuid4())
        data_name = '%s-data' % name
        processors_name = '%s-processors' % name

        pipeline_definition = self.get_definition()

        with make_repo(clients, data_name) as data_repo, \
                make_repo(clients, processors_name) as processors_repo:
            session = {
                'name': name,
                'data': data_repo,
                'processors': processors_repo
            }
            with make_pipeline(clients, pipeline_definition, session) as pipeline:
                session['pipeline'] = pipeline
                yield session

    async def run(self, filename, workflow_module, bucket=None):
        """Execute the pipeline on a Pachyderm cluster."""

        with self.make_session() as session:
            with open(workflow_module, 'r') as file_obj:
                self.add_processor('processor', file_obj.read().encode('utf-8'), session)

            if bucket:
                content = filename
            else:
                with open(filename, 'r') as file_obj:
                    content = file_obj.read().encode('utf-8')

            # TODO: safely set file extension
            self.add_data('data.csv', content, session, bucket)

            monitor_pipeline, monitor_output = await self.monitor_pipeline(session)

            commit = await monitor_output

            monitor_pipeline.cancel()

            results = await self.get_output(session)

        return results

    @staticmethod
    async def _wait_for_pipeline(pipeline, retry_count, retry_processing_count, retry_delay):
        """Wait until pipeline has completed."""

        async def _tick_callback():
            sys.stdout.write('.')
            sys.stdout.flush()
            await asyncio.sleep(retry_delay)

        # Wait for pipeline run to start
        await pipeline.wait_for_run(
            retry_count,
            tick_callback=_tick_callback,
            error_suffix=" to start"
        )

        # Wait for pipeline run to finish
        return await pipeline.wait_for_run(
            retry_processing_count,
            (pypachy.JOB_STARTING, pypachy.JOB_RUNNING),
            tick_callback=_tick_callback,
            error_suffix=" to finish"
        )

    async def watch_for_output(self, queue, session):
        commit_queue = await session['pipeline'].watch_commits()
        input_repos = {session['data'].get_name(), session['processors'].get_name()}

        provenance = False
        while not input_repos == provenance:
            commit = await commit_queue.get()
            provenance = {p['repo_name'] for p in commit.get_provenance()}

        await queue.put(commit)

        await session['pipeline'].stop_watching_commits()

    async def monitor_pipeline(self, session):
        """Check pipeline for completion and process results."""

        loop = asyncio.get_event_loop()

        # Wait for the output, which Pachyderm lets us subscribe to,
        # and poll the job, in case there isn't any

        queue = asyncio.Queue()
        asyncio.ensure_future(self.watch_for_output(queue, session))
        pipeline_fut = asyncio.ensure_future(self.wait_for_pipeline(session))

        return (pipeline_fut, queue.get())

    async def get_output(self, session):
        output = session['pipeline'].pull_output('/doorstep.out')

        return ['\n'.join([line.decode('utf-8') for line in output])]

    def wait_for_commit(self, session):
        for commit in session['pipeline'].subscribe_output_commit():
            print(commit.get_provenance())

    async def wait_for_pipeline(self, session):
        try:
            job = await self._wait_for_pipeline(
                session['pipeline'],
                self._retry_count,
                self._retry_processing_count,
                self._retry_delay
            )
        except JobFailedException as exc:
            logs = exc.logs()
            if logs:
                print(logs[0])
                print('\n'.join([log.message.rstrip() for log in logs]))
            raise exc
