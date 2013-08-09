import os, sys, getpass, time
import wasanbon
import wasanbon.core.project as prj

class Command(object):
    def __init__(self):
        pass

    
    def execute_with_argv(self, argv, verbose, force, clean):

        if argv[2] == 'create':
            wasanbon.arg_check(argv, 4)

            sys.stdout.write(' - Creating workspace %s\n' % argv[3])
            proj = prj.create_project(argv[3], verbose=verbose)

        elif argv[2] == 'unregister':
            wasanbon.arg_check(argv, 4)

            sys.stdout.write(' - Removing workspace %s\n' % argv[3])
            proj = prj.get_project(argv[3], verbose=verbose)
            proj.unregister(verbose=verbose, clean=clean)


        elif argv[2] == 'list':
            print ' - Listing projects.'
            projs = prj.get_projects(verbose=verbose)
            for proj in projs:
                sys.stdout.write(' ' + proj.name + ' '*(10-len(proj.name)) + ':' + proj.path + '\n')

        elif argv[2] == 'directory':
            try:
                proj = prj.get_project(argv[3].strip())
                print proj.path
            except:
                print '.'

        elif argv[2] == 'repository':
            print ' - Listing Project Repositories'
            repos = prj.get_repositories(verbose=verbose)
            for repo in repos:
                print ' ' + repo.name + ' ' * (24-len(repo.name)) + ' : ' + repo.description
            return

        elif argv[2] == 'clone':
            wasanbon.arg_check(argv,4)

            print ' - Cloning Project from Repository'
            repo = prj.get_repository(argv[3], verbose=verbose)
            proj = repo.clone(verbose=verbose)

        elif argv[2] == 'fork':
            wasanbon.arg_check(argv, 4)

            print ' - Forking Project from Repository'
            user, passwd = wasanbon.user_pass()
            original_repo = prj.get_repository(argv[3], verbose=verbose)
            repo = original_repo.fork(user, passwd, verbose=verbose)
            proj = repo.clone(verbose=verbose)
