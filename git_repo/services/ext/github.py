#!/usr/bin/env python

import logging
log = logging.getLogger('git_repo.github')

from ..service import register_target, RepositoryService
from ...exceptions import ResourceError, ResourceExistsError, ResourceNotFoundError

import github3

from git.exc import GitCommandError

@register_target('hub', 'github')
class GithubService(RepositoryService):
    fqdn = 'github.com'

    def __init__(self, *args, **kwarg):
        self.gh = github3.GitHub()
        super(GithubService, self).__init__(*args, **kwarg)

    def connect(self):
        try:
            self.gh.login(token=self._privatekey)
            self.username = self.gh.user()
        except github3.models.GitHubError as err:
            if err.code is 401:
                if not self._privatekey:
                    raise ConnectionError('Could not connect to Github. '
                                          'Please configure .gitconfig '
                                          'with your github private key.') from err
                else:
                    raise ConnectionError('Could not connect to Github. '
                                          'Check your configuration and try again.') from err

    def create(self, user, repo, add=False):
        try:
            self.gh.create_repo(repo)
        except github3.models.GitHubError as err:
            if err.code == 422 or err.message == 'name already exists on this account':
                raise ResourceExistsError("Project already exists.") from err
            else: # pragma: no cover
                raise ResourceError("Unhandled error.") from err
        if add:
            self.add(user=user, repo=repo, tracking=self.name)

    def fork(self, user, repo, branch='master', clone=False):
        log.info("Forking repository {}/{}…".format(user, repo))
        try:
            fork = self.gh.repository(user, repo).create_fork()
        except github3.models.GitHubError as err:
            if err.message == 'name already exists on this account':
                raise ResourceExistsError("Project already exists.") from err
            else: # pragma: no cover
                raise ResourceError("Unhandled error: {}".format(err)) from err
        self.add(user=user, repo=repo, name='upstream', alone=True)
        remote = self.add(repo=repo, user=self.username, tracking=self.name)
        if clone:
            self.pull(remote, branch)
        log.info("New forked repository available at {}/{}".format(self.url_ro,
                                                                   fork.full_name))

    def delete(self, repo, user=None):
        if not user:
            user = self.username
        try:
            repository = self.gh.repository(user, repo)
            if repository:
                result = repository.delete()
            if not repository or not result:
                raise ResourceNotFoundError('Cannot delete: repository {}/{} does not exists.'.format(user, repo))
        except github3.models.GitHubError as err: # pragma: no cover
            if err.code == 403:
                raise ResourcePermissionError('You don\'t have enough permissions for deleting the repository. '
                                              'Check the namespace or the private token\'s privileges') from err
            raise ResourceError('Unhandled exception: {}'.format(err)) from err

    def get_repository(self, user, repo):
        repository = self.gh.repository(user, repo)
        if not repository:
            raise ResourceNotFoundError('Cannot delete: repository {}/{} does not exists.'.format(user, repo))
        return repository

    def request_list(self, user, repo):
        repository = self.gh.repository(user, repo)
        for pull in repository.iter_pulls():
            yield ( str(pull.number), pull.title, pull.links['issue'] )

    def request_fetch(self, user, repo, request, pull=False):
        if pull:
            raise NotImplementedError('Pull operation on requests for merge are not yet supported')
        log.info('remotes: {}'.format(self.repository.remotes))
        try:
            for remote in self.repository.remotes:
                log.info('request_fetch, remote_name {}'.format(remote.name))
                if remote.name == self.name:
                    local_branch_name = 'request-{}'.format(request)
                    self.fetch(
                        remote,
                        'pull/{}/head'.format(request),
                        local_branch_name
                    )
                    return local_branch_name
            else:
                raise ResourceNotFoundError('Could not find remote {}'.format(self.name))
        except GitCommandError as err:
            if 'Error when fetching: fatal: Couldn\'t find remote ref' in err.command[0]:
                raise ResourceNotFoundError('Could not find opened request #{}'.format(request)) from err
            raise err

    @property
    def user(self):
        return self.gh.user().name

