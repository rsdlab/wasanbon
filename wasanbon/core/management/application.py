#!/usr/bin/env python

import os, sys, types, optparse, traceback
import wasanbon.core.management
#import wasanbon.core.management.commands
#import wasanbon.core.management.admin


"""
option_list = (
        make_option('-v', '--verbosity', action='store', dest='verbosity', default='1',
            type='choice', choices=['0', '1', '2', '3'],
            help='Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output'),
        make_option('--settings',
            help='The Python path to a settings module, e.g. "myproject.settings.main". If this isn\'t provided, the DJANGO_SETTINGS_MODULE environment variable will be used.'),
        make_option('--pythonpath',
            help='A directory to add to the Python path, e.g. "/home/djangoprojects/myproject".'),
        make_option('--traceback', action='store_true',
            help='Print traceback on exception'),
    )

"""

def autocomplete(self):
    if 'TPR_AUTO_COMPLETE' not in os.environ:
        return
    
    cwords = os.environ['COMP_WORDS'].split()[1:]
    cword = int(os.environ['COMP_CWORDS'])
    
    try:
        curr = cwords[cword-1]
    except IndexError:
        curr = ''
        pass

    subcommands = get_commands().keys() + ['help']
    options = [('--help', None)]
    
    if cword == 1:
        print ' '.join(sorted(filtar(lambda x: x.startswith(curr), subcommands)))
    elif cwords[0] in subcommands and cwords[0] != 'help':
        subcommand_cls = self
        pass
    pass

    
def get_subcommand_list(package):
    """
    Get Subcommand from Directory
    wasanbon/core/management/%package%
    package can be admin or commands.
    """
    #mod = __import__('wasanbon.core.management.' + package)
    ret = [x[:len(x)-3] for x in os.listdir(os.path.join(wasanbon.core.management.__path__[0], package)) if x.endswith('.py') and not x.startswith("__")]
    ret.append('help')
    return ret

def show_help_description(subcommand):
    sys.stdout.write("\nUsage : %s %s [args...]\n"%  (os.path.basename(sys.argv[0]), subcommand))
    help =  wasanbon.get_help_text(['help','command', 'description', subcommand])
    if type(help) is types.ListType:
        for h in help:
            print "  " +  h
    else:
        print "  " +  help

    print "\n\nOptions:"
    print "  -h, --help   Show This Help"

class ArgumentParser(optparse.OptionParser):
    def __init__(self, usage, add_help_option):
        optparse.OptionParser.__init__(self,usage=usage, add_help_option=add_help_option)
        self.__usage = usage
    
    def print_help(self):
        print self.__usage
        pass

def execute(argv=None):
    if argv == None:
        argv = sys.argv
    command = os.path.basename(argv[0])

    if command == 'wasanbon-admin.py':
        package = 'admin'
    else:
        package = 'commands'

    opts = get_subcommand_list(package)
    try:
        usage  = wasanbon.get_help_text(['help', 'general', 'command'])
        usage  = usage + '\n\nsubcommand:\n'
        for opt in opts:
            usage = usage + ' - ' + opt + ' '*(15-len(opt)) + ':' + wasanbon.get_help_text(['help', 'general', 'brief', opt]) + '\n'
    except:
        usage = "wasanbon-admin.py"

    parser = ArgumentParser(usage=usage, add_help_option=False)
    try:

        #parser.disable_interspersed_args()
        parser.add_option('-h', '--help', help=wasanbon.get_help_text(['help', 'help']), action='store_true', default=False, dest='help_flag')
        parser.add_option('-v', '--verbose', help=wasanbon.get_help_text(['help', 'verbose']), action='store_true', default=False, dest='verbose_flag')
        parser.add_option('-c', '--clean', help=wasanbon.get_help_text(['help', 'clean']), action='store_true', default=False, dest='clean_flag')
        parser.add_option('-f', '--force', help=wasanbon.get_help_text(['help', 'force']), action='store_true', default=False, dest='force_flag')
        parser.add_option('-l', '--longformat', help=wasanbon.get_help_text(['help', 'long']), action='store_true', default=False, dest='long_flag')
        parser.add_option('-i', '--interactive', help=wasanbon.get_help_text(['help', 'interactive']), action='store_true', default=False, dest='interactive_flag')
        parser.add_option('-a', '--alternative', help="command alternative", action='store_true', default=False, dest='alter_flag')

    except:
        traceback.print_exc()
        pass

    try:
        options, args = parser.parse_args(argv[:])

        if options.help_flag == True:
            show_help_description(subcommand)
            return

        
    except:
        traceback.print_exc()
        #return
        pass

    index = 1
    try:
        while args[index].startswith('-'):
            index = index + 1
        subcommand = args[index]

    except IndexError:
        if len(args) == 1 and options.alter_flag:
            # list subcommands
            subcommands = opts#get_subcommand_list(package)
            for i, subcmd in enumerate(subcommands):
                sys.stdout.write(subcmd)
                if i == len(subcommands) -1:
                    sys.stdout.write('\n')
                else:
                    sys.stdout.write(' ')

            return
        subcommand = 'help'

    #opts = get_subcommand_list(package)
    if not subcommand in opts:
        subcommand = 'help'
    

    if subcommand == 'help':
        parser.print_help()
        return

    try:
        index = index + 1
        while args[index].startswith('-'):
            index = index + 1
        arg1 = args[index]
        if arg1 == 'help': 
            options.help_flag = True
    except:
        pass


    module_name = 'wasanbon.core.management.%s.%s' % (package, subcommand)
    __import__(module_name)
    comm = sys.modules[module_name].Command()

    try:
        if options.alter_flag:
            alternative = comm.alternative()
            for i, cmd in enumerate(alternative):
                sys.stdout.write(cmd)
                if i == len(alternative) - 1:
                    sys.stdout.write('\n')
                else:
                    sys.stdout.write(' ')
            pass
        else:
            comm.execute_with_argv(args, verbose=options.verbose_flag, clean=options.clean_flag, force=options.force_flag)
    except wasanbon.InvalidUsageException, ex:
        show_help_description(subcommand)
        
    except wasanbon.WasanbonException, ex:
        if options.verbose_flag:
            traceback.print_exc()
        sys.stdout.write(' # Error. %s\n' % ex.msg())
    except Exception, ex:
        traceback.print_exc()
    pass

