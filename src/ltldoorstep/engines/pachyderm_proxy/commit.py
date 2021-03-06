"""Proxy class for a Pachyderm Commit."""

class PachydermCommit:
    """Proxy class for a Pachyderm Commit."""

    def __init__(self, clients, repo, name, provenance=None):
        self._repo = repo
        self._name = name
        self._clients = clients
        self._provenance = provenance

    def put_file_bytes(self, filename, content):
        """Send a file to Pachyderm bytewise."""

        self._clients['pfs'].put_file_bytes(
            self.get_full_name(),
            filename,
            content
        )

    def put_file_url(self, filename, url):
        """Send a file to Pachyderm from a third-party service."""

        self._clients['pfs'].put_file_url(
            self.get_full_name(),
            filename,
            url
        )

    def get_name(self):
        """Get the name of this commit."""

        return self._name

    def get_full_name(self):
        """Get the name of this commit, including the repo."""

        return '%s/%s' % (self._repo, self._name)

    def get_provenance(self):
        """Get provenance of this commit, if any."""

        return self._provenance

    def pull_file(self, path):
        """Retrieve a file from Pachyderm."""

        return self._clients['pfs'].get_file(self.get_full_name(), path)

    @classmethod
    def from_raw(cls, commit, clients):
        """Turn a gRPC commit into our own object."""

        provenance = None

        if commit.provenance:
            provenance = [{
                'id': prov.id,
                'repo_name': prov.repo.name
            } for prov in commit.provenance]

        return cls(
            clients,
            commit.commit.repo,
            commit.commit.id,
            provenance
        )
