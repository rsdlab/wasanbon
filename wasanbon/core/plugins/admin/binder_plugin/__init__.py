import os, sys, types, subprocess, yaml
import wasanbon
from wasanbon.core.plugins import PluginFunction, manifest

class Plugin(PluginFunction):

    def __init__(self):
        #PluginFunction.__init__(self)
        super(Plugin, self).__init__()
        pass

    def depends(self):
        return ['admin.environment', 'admin.git']

    def _print_alternatives(self):
        print 'hoo'
        print 'foo'
        print 'hoge'
        print 'yah'

    @manifest
    def update(self, argv):
        """ This is help text
        """
        options, argv = self.parse_args(argv[:], self._print_alternatives)
        verbose = options.verbose_flag # This is default option
        #import binder
        path = os.path.join(admin.environment.setting_path, '..', 'repository.yaml')
        download_repositories(path, verbose=verbose)

    @manifest
    def list(self, args):
        options, argv = self.parse_args(args)
        verbose = options.verbose_flag
        binders = self.get_binders(verbose=verbose)
        print binders
        return 0
    
    @manifest
    def rtcs(self, args):
        self.parser.add_option('-l', '--long', help='Long Format (default=False)', default=False, action='store_true', dest='long_flag')
        options, argv = self.parse_args(args)
        verbose = options.verbose_flag
        long = options.long_flag

        binders = self.get_binders(verbose=verbose)
        for binder in binders:
            for rtc in binder.rtcs:
                if not long:
                    print ' - %s' % rtc.name
                else:
                    print '%s :' % rtc.name
                    print '  %s : %s' % ('url', rtc.url)
                    print '  %s : %s' % ('type', rtc.type)
                    print '  %s : %s' % ('description', rtc.description)
                    print '  %s : %s' % ('platform', rtc.platform)
            
        return 0
    
    @manifest
    def packages(self, args):
        self.parser.add_option('-l', '--long', help='Long Format (default=False)', default=False, action='store_true', dest='long_flag')
        options, argv = self.parse_args(args)
        verbose = options.verbose_flag
        long = options.long_flag


        binders = self.get_binders(verbose=verbose)
        for binder in binders:
            for package in binder.packages:
                if not long:
                    print ' - %s' % package.name
                else:
                    print '%s :' % package.name
                    print '  %s : %s' % ('url', package.url)
                    print '  %s : %s' % ('type', package.type)
                    print '  %s : %s' % ('description', package.description)
                    print '  %s : %s' % ('platform', package.platform)

        return 0

    def get_binders(self, verbose=False):
        return get_binders(verbose=verbose)

    def get_package_repos(self, verbose=False):    
        return get_package_repos(verbose=verbose)
            
    def get_rtc_repos(self, verbose=False):
        binders = self.get_binders(verbose=verbose)
        return [r for b in binders for r in b.rtcs]
            
        
    def get_package_repo(self, name, verbose=False):
        return get_package_repo(name, verbose=verbose)

    def Repository(self, name, type, platform, url, description):
        return Repository(name=name, 
                          type=type,
                          platform=platform,
                          url=url,
                          description=description)

_owner_sign = '_owner'

#plugin_obj = None

class Repository(object):
    def __init__(self, name, type, platform, url, description):

        self._name = name
        self._url  = url
        self._type = type
        self._platform = platform
        self._description = description
        pass

    @property
    def name(self):
        return self._name

    @property
    def url(self):
        return self._url

    @property
    def basename(self):
        b = os.path.basename(self.url)
        if b.endswith('.git'):
            b = b[:-4]
        return b

    @property
    def type(self):
        return self._type

    @property
    def platform(self):
        return self._platform
    
    @property
    def description(self):
        return self._description
    

class Binder(object):
    def __init__(self, owner, path):
        self._owner = owner
        self._path = path
        self._rtcs = None
        self._packages = None

    @property
    def rtcs(self):
        if self._rtcs is None:
            import yaml
                     
            self._rtcs = []
            path_ = os.path.join(self.path, 'rtcs')
            for f in os.listdir(path_):
                filepath = os.path.join(path_, f)
                d = yaml.load(open(filepath, 'r'))
                if type(d) is types.DictType:
                    for name, v in d.items():
                        self._rtcs.append(Repository(name = name,
                                                     description = v['description'],
                                                     type = v['type'],
                                                     platform = v['platform'],
                                                     url = v['url']))


        return self._rtcs

    @property
    def packages(self):
        if self._packages is None:
            import yaml
                     
            self._packages = []
            path_ = os.path.join(self.path, 'packages')
            for f in os.listdir(path_):
                filepath = os.path.join(path_, f)
                d = yaml.load(open(filepath, 'r'))
                if type(d) is types.DictType:
                    for name, v in d.items():
                        self._packages.append(Repository(name = name,
                                                     description = v['description'],
                                                     type = v['type'],
                                                     platform = v['platform'],
                                                     url = v['url']))


        return self._packages

    @property
    def owner(self):
        return self._owner

    @property
    def path(self):
        return self._path



def get_package_repos(verbose=False):
    binders = get_binders(verbose=verbose)
    package_repos = []
    for binder in binders:
        package_repos = package_repos + binder.packages
        
    return package_repos

def get_package_repo(name, verbose=False):
    for package_repo in get_package_repos(verbose=verbose):
        if package_repo.name == name:
            return package_repo

    import wasanbon
    raise wasanbon.RepositoryNotFoundException()


def get_binders(verbose=False):
    path_ = repository_path()    
    binders = []
    for name in os.listdir(path_):
        namep = os.path.join(path_, name)
        for b in os.listdir(namep):
            bp = os.path.join(namep, b)
            if 'setting.yaml' in os.listdir(bp):
                binders.append(Binder(name, bp))
    return binders

def get_default_repo_directory():
    import wasanbon
    _default_repo_directory = os.path.join(wasanbon.home_path, 'binder')
    if not os.path.isdir(_default_repo_directory):
        os.mkdir(_default_repo_directory)

    return _default_repo_directory

def download_repositories(setting_filepath, verbose=False, force=False):
    if verbose:
        sys.stdout.write(' - Downloading Repositories....\n')
        sys.stdout.write('    - Opening setting file in %s\n' % setting_filepath)

    with open(setting_filepath, 'r') as repo_setting:
        for name, value in yaml.load(repo_setting).items():
            if verbose: sys.stdout.write('    - Repository : %s\n' % name)
            urls = value['url']
            if type(urls) is not types.ListType:
                urls = [urls]
            for url in urls:
                download_repository(url, verbose=verbose, force=force)
    return True

def repository_path(url=None):
    root = get_default_repo_directory()
    if url:
        root = os.path.join(root, url.split('/')[-2])
    return root
                
def download_repository(url, target_path='',verbose=False, force=False):
    _repository_path = repository_path(url)
    if not target_path:
        target_path = os.path.join(_repository_path, url.split('/')[-1])
    if verbose:
        sys.stdout.write('    - Downloading repository %s\n' % url)
        sys.stdout.write('        into %s\n' % target_path)
    
    git_command = admin.git.git_command
    if os.path.isdir(target_path):
        if os.path.isdir(os.path.join(target_path, '.git')):
            git_command(['pull'], verbose=True, path=target_path)
        else: # Directory exists but not git repository dir
            git_command(['clone', url, target_path], verbose=verbose)
        pass
    else:
        if not os.path.isdir(target_path):
            os.makedirs(target_path)
            pass
        git_command(['clone', url, target_path], verbose=verbose)
        pass

    if verbose:
        sys.stdout.write('    - Parsing child Binder\n')
    setting_file_path = os.path.join(target_path, 'setting.yaml')
    if os.path.isfile(setting_file_path):
        with open(setting_file_path, 'r') as setting_file:
            setting = yaml.load(setting_file)
            if type(setting) is types.DictType:
                child_repos = setting.get('child_binder', [])
                for repo in child_repos:
                    download_repository(repo, verbose=verbose, force=force)
    pass

