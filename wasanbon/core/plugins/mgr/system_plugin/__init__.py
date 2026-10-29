import os
import sys
import signal
import time
import traceback
import threading

import wasanbon
from wasanbon.core.plugins import PluginFunction, manifest

import subprocess
import xml.etree.ElementTree as ET
import re

endflag = False
ev = threading.Event()


class Plugin(PluginFunction):
    """ System Management (Launch, Installing RTCs, Configuration, and Connection) Plugin. """

    def __init__(self):
        # PluginFunction.__init__(self)
        super(Plugin, self).__init__()
        pass

    def depends(self):
        return ['admin.environment',
                'admin.package',
                'admin.rtc',
                'admin.systeminstaller',
                'admin.systemlauncher',
                'admin.systembuilder',
                'admin.nameserver',
                'admin.systemeditor',
                'admin.rtcconf']

    def _print_rtcs(self, args):
        pack = admin.package.get_package_from_path(os.getcwd())
        for rtc in admin.rtc.get_rtcs_from_package(pack):
            print(rtc.rtcprofile.basicInfo.name)

    @manifest
    def run(self, args):
        """ Launch System.
        $ ./mgr.py system run <SYSTEM_FILENAME>
        """
        self.parser.add_option('-b', '--background', help='Launch in background(default=False)',
                               default=False, action='store_true', dest='background_flag')
        self.parser.add_option('-w', '--wakeuptimeout', help='Timeout of Sleep Function when waiting for the wakeup of RTC-Daemons',
                               default=5, dest='wakeuptimeout', action='store', type='float')
        # self.parser.add_option('-f', '--file', help='Build System with Specific RTSProfile (must be placed in system_dir',
        #                        default=None, dest='systemfile', action='store', type='string')
        self.parser.add_option('-p', '--plain', help='Plain Launch. Without building/activating system.',
                               default=False, dest='plain_flag', action='store_true')
        self.parser.add_option('-q', '--quiet', help='Build system but do not activate RTCs.', default=False, dest='quiet_flag', action='store_true')
        options, argv = self.parse_args(args[:])
        verbose = options.verbose_flag
        background = options.background_flag
        wakeuptimeout = options.wakeuptimeout
        plain = options.plain_flag
        quiet = options.quiet_flag
        wasanbon.arg_check(argv, 4)

        if plain:
            quiet = True

        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)

        systemfile_name = argv[3]
        print(systemfile_name)
        if not systemfile_name.endswith(".xml"):
            systemfile_name += ".xml"
        systemfile = os.path.join(package.get_systempath(), systemfile_name)

        ##RTC_CHECK
        # pack = admin.package.get_package_from_path(os.getcwd())
        rtcs = admin.rtc.get_rtcs_from_package(package, verbose=verbose)
        self.rtc_check="no"
        if rtcs:
            for rtc in rtcs:
                xml_path=os.path.join(package.get_rtcpath(),rtc.rtcprofile.basicInfo.name,"RTC.xml")
                if os.path.isfile(xml_path):
                    self.rtc_check="ok"
                else:
                    self.rtc_check="no"

        ##ROS_CHECK
        ROSs=False
        ros_version = None
        package_xml_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), 'package.xml')
        if package_xml_dirs:
            file_path = f"{package_xml_dirs[0]}/package.xml"
            ROSs = self.check_catkin_buildtool(file_path)
            ros_version = self.get_ros_version(file_path)

        print(f"ROS version: {ros_version}")

        ##RUN_START
        if ros_version == 1:
            if background:
                node_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".launch")
                print(node_dirs)
                package_name = os.path.basename(os.path.dirname(node_dirs[0]))
                print(package_name)

                ##launch名取得
                launch_file_path = node_dirs[0]+"/"+argv[3]+".launch"
                print(launch_file_path)
                nodes = self.extract_node_names_from_launch(launch_file_path)
                print(nodes)

                ##roslaunch
                self.launch_ros_b(package_name, argv[3] + ".launch")
                #rosnode list
                check=self.check_nodes_are_running(nodes)
                print(check)

            else:
                node_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".launch")

                ##roslaunch
                package_name = os.path.basename(os.path.dirname(node_dirs[0]))
                self.launch_ros(package_name, argv[3] + ".launch")

        elif ros_version == 2:
            launch_name = argv[3] + ".launch.py"
            node_dirs = self.find_package_xml(
                os.path.dirname(package.get_rtcpath()),
                launch_name
            )

            if not node_dirs:
                print(f"ROS2 launch file not found: {launch_name}")
                return -1

            print(node_dirs)
            package_name = os.path.basename(os.path.dirname(node_dirs[0]))
            print(package_name)

            if background:
                ##ros2 launch
                self.launch_ros2_b(package_name, launch_name)
            else:
                ##ros2 launch
                self.launch_ros2(package_name, launch_name)

        elif self.rtc_check=="ok":
            started_nss = []
            nss = admin.nameserver.get_nameservers_from_package(package, verbose=verbose)
            for ns in nss:
                if not admin.nameserver.is_running(ns, verbose=verbose, try_count=5, interval=5.0):
                    sys.stdout.write('## Nameserver %s is not running.\n' % ns.path)
                    if ns.address == 'localhost' or ns.address == '127.0.0.1':
                        if verbose:
                            '# Start Nameserver %s\n' % ns.path
                        admin.nameserver.launch(ns, verbose=verbose)
                        started_nss.append(ns)
                        wasanbon.sleep(5.0)

            global endflag
            endflag = False
            retval = 0
            try:
                processes = admin.systemlauncher.launch_system(package, verbose=verbose)
                wasanbon.sleep(wakeuptimeout)
                if not plain:
                    admin.systembuilder.build_system(package,
                                                     verbose=verbose,
                                                     system_file=systemfile)

                    if not quiet:
                        admin.systembuilder.activate_system(package,
                                                           verbose=verbose,
                                                           system_file=systemfile)

                if background:
                    return 0

                def signal_action(num, frame):
                    print(' - SIGINT captured')
                    ev.set()
                    global endflag
                    endflag = True

                signal.signal(signal.SIGINT, signal_action)
                if sys.platform == 'win32':
                    sys.stdout.write(' - Escaping SIGBREAK...\n')
                    signal.signal(signal.SIGBREAK, signal_action)

                endflag = False
                while not endflag:
                    try:
                        time.sleep(0.1)
                        languages = ['Java', 'Python', 'C++']
                        stopped = []
                        for l in languages:
                            stopped.append(not admin.systemlauncher.is_rtcd_launched(package, l, verbose=verbose))
                        stopped.append(not admin.systemlauncher.is_standalone_rtcs_launched(package, verbose=verbose))
                        if all(stopped):
                            endflag = True
                    except IOError as e:
                        print(e)

                if not plain:
                    admin.systembuilder.deactivate_system(package,
                                                         verbose=verbose,
                                                         system_file=systemfile)

            except wasanbon.BuildSystemException:
                sys.stdout.write('# Build System Failed.\n')
                traceback.print_exc()
                retval = -1
            except Exception:
                traceback.print_exc()
                retval = -1
            finally:
                try:
                    if not background:
                        admin.systemlauncher.exit_all_rtcs(package, verbose=verbose)
                        admin.systemlauncher.terminate_system(package, verbose=verbose)
                except Exception:
                    traceback.print_exc()
                    retval = -1

            for ns in started_nss:
                if verbose:
                    '# Stopping Nameserver %s\n' % ns.path
                admin.nameserver.terminate(ns, verbose=verbose)

            return retval

    def check_nodes_are_running(self, node_names, timeout_sec=10):
        """
        最大 timeout_sec 秒間、rosnode list を監視して
        指定されたすべてのノードが起動されているか確認

        Args:
            node_names (List[str]): ノード名のリスト（例: ['talker', 'listener']）
            timeout_sec (int): 最大監視時間（秒）

        Returns:
            bool: すべてのノードが見つかれば True、1つでも見つからなければ False
        """
        full_names = {f"/{name}" for name in node_names}
        start_time = time.time()

        while time.time() - start_time < timeout_sec:
            try:
                result = subprocess.run(["rosnode", "list"], capture_output=True, text=True)
                running_nodes = set(result.stdout.splitlines())

                if full_names.issubset(running_nodes):
                    print(f"すべてのノードが見つかりました: {', '.join(full_names)}")
                    return True

            except FileNotFoundError:
                print("'rosnode' コマンドが見つかりません。")
                return False
            except Exception as e:
                print(f"エラー: {e}")
                return False

            time.sleep(0.5)

        print(f"タイムアウト: {timeout_sec} 秒以内にすべてのノードは見つかりませんでした。")
        missing = full_names - running_nodes
        print(f"見つからなかったノード: {', '.join(missing)}")
        return False

    def _parse_launch_args(self,root):
        arg_dict = {}
        for arg in root.iter('arg'):
            name = arg.attrib.get('name')
            default = arg.attrib.get('default')
            if name and default:
                arg_dict[name] = default
        return arg_dict

    def expand_arg_variables(self, text, arg_dict):
        def replacer(match):
            var_name = match.group(1)
            return arg_dict.get(var_name, match.group(0))
        return re.sub(r"\$\(\s*arg\s+([a-zA-Z0-9_]+)\s*\)", replacer, text)
    def extract_node_names_from_launch(self, file_path, visited=None, parent_args=None):
        if visited is None:
            visited = set()
        if parent_args is None:
            parent_args = {}

        node_names = []
        file_path = os.path.abspath(file_path)

        if file_path in visited:
            return node_names
        visited.add(file_path)

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            local_args = self._parse_launch_args(root)
            merged_args = parent_args.copy()
            merged_args.update(local_args)

            for node in root.iter('node'):
                name = node.attrib.get('name')
                if name:
                    name = self.expand_arg_variables(name, merged_args)

                    if re.search(r"\$\(\s*anon\s+[a-zA-Z0-9_]+\s*\)", name):
                        print(f" anonノードは除外: {name}")
                        continue

                    node_names.append(name)

            for include in root.iter('include'):
                included_file = include.attrib.get('file')
                if included_file is None:
                    continue

                included_file = self.expand_arg_variables(included_file, merged_args)

                if '$(find' in included_file:
                    try:
                        pkg = included_file.split('$(find')[1].split(')')[0].strip()
                        relative_path = included_file.split(')')[-1]
                        pkg_path = subprocess.check_output(['rospack', 'find', pkg], text=True).strip()
                        included_file_path = os.path.join(pkg_path, relative_path.lstrip('/'))
                    except subprocess.CalledProcessError:
                        print(f"パッケージ {pkg} が見つかりません")
                        continue
                else:
                    included_file_path = os.path.join(os.path.dirname(file_path), included_file)

                if not os.path.isfile(included_file_path):
                    print(f"含まれる launch ファイルが存在しないためスキップ: {included_file_path}")
                    continue

                node_names += self.extract_node_names_from_launch(included_file_path, visited, merged_args)

        except Exception as e:
            print(f"エラー（{file_path}）: {e}")

        return node_names

    def find_package_xml(self, directory, object):
        package_dirs = []
        for root, dirs, files in os.walk(directory):
            if object in files:
                package_dirs.append(root)
        return package_dirs

    def check_catkin_buildtool(self, file_path):
        try:
            # XMLファイルを読み込む
            tree = ET.parse(file_path)
            root = tree.getroot()

            # <buildtool_depend>タグを取得
            buildtool_dependencies = root.findall(".//buildtool_depend")

            # catkinが存在するか確認
            for dep in buildtool_dependencies:
                if dep.text and dep.text.strip() == "catkin":
                    return True

            return False

        except ET.ParseError as e:
            return False
        except FileNotFoundError:
            return False

    def get_ros_version(self, file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            buildtool_dependencies = root.findall(".//buildtool_depend")

            for dep in buildtool_dependencies:
                if not dep.text:
                    continue

                buildtool = dep.text.strip()

                if buildtool == "catkin":
                    return 1
                elif buildtool in ("ament_cmake", "ament_python"):
                    return 2

            return None

        except (ET.ParseError, FileNotFoundError):
            return None

    def check_dependencies(self, file_path, dependencies_to_check):
        try:
            import xml.etree.ElementTree as ET
            # XMLファイルを読み込む
            tree = ET.parse(file_path)
            root = tree.getroot()

            # 全ての<depend>, <build_depend>, <exec_depend>, <build_export_depend>タグを取得
            dependencies = root.findall(".//depend") + root.findall(".//build_depend") + \
                        root.findall(".//exec_depend") + root.findall(".//build_export_depend")

            # 依存関係名をリスト化
            dependency_names = {dep.text.strip() for dep in dependencies if dep.text}

            # 指定された依存関係が存在するかチェック
            found_dependencies = [dep for dep in dependencies_to_check if dep in dependency_names]

            if found_dependencies:
                # print("This is ROS Package")
                return True
            else:
                # print("This is not ROS Package")
                return False
        except ET.ParseError as e:
            # print(f"Error parsing XML: {e}")
            return False
        except FileNotFoundError:
            # print(f"File not found: {file_path}")
            return False

    def add_execute_permission(self, directory):
        try:
            # chmod +x コマンドを subprocess で実行
            command = f"chmod +x {directory}/*.py"
            # command = f"chmod +x {directory}/*.cpp"
            result = subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # 成功した場合
            if result.returncode == 0:
                print(f"Execute permission added to all .py files in {directory}")
                print(result.stdout)
            else:
                print(f"Error while adding execute permission:\n{result.stderr}")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    def launch_ros(self, package_name, node_name):
        try:
            # roslaunchコマンドの実行
            command = ["roslaunch", package_name, node_name]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            sys.stdout.write(f"\n--- Debug: Inside launch_ros ---\n")
            sys.stdout.flush()

            print(f"Running ROS node: {node_name} from package: {package_name}")

            # 標準出力と標準エラーをリアルタイムで監視
            while True:
                output = process.stdout.readline()
                error = process.stderr.readline()

                # 標準出力の処理
                if output:
                    print(output, end="", flush=True)

                # 標準エラーの処理
                if error:
                    print(f"[ERROR]: {error}", end="", file=sys.stderr, flush=True)

                # プロセスが終了している場合ループを終了
                if output == "" and error == "" and process.poll() is not None:
                    break

        except KeyboardInterrupt:
            print("\nNode execution interrupted by user.")
            process.terminate()  # プロセスを終了
            process.wait()       # 終了を待機
        except FileNotFoundError:
            print("Error: 'rosrun' command not found. Is ROS installed and sourced?")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            # プロセスがまだ動作中の場合は終了
            if process and process.poll() is None:
                process.terminate()
                process.wait()

    def launch_ros_b(self, package_name, node_name):
        try:
            # roslaunchコマンドの実行
            command = ["roslaunch", package_name, node_name]
            # process = subprocess.Popen(
            #     command,
            #     stdout=subprocess.PIPE,
            #     stderr=subprocess.PIPE,
            #     text=True,
            # )
            process = subprocess.Popen(command)

            print(f"Running ROS node: {node_name} from package: {package_name}")

        except FileNotFoundError:
            print("Error: 'rosrun' command not found. Is ROS installed and sourced?", flush=True)
        except Exception as e:
            print(f"An unexpected error occurred in run_ros_node_b: {e}", flush=True)
            traceback.print_exc()


    def launch_ros2(self, package_name, launch_name):
        process = None
        try:
            command = ["ros2", "launch", package_name, launch_name]
            print(f"Running ROS2 launch: {launch_name} from package: {package_name}", flush=True)
            env = self._get_ros2_env()
            process = subprocess.Popen(command, env=env)
            process.wait()
        except KeyboardInterrupt:
            print("\nROS2 launch interrupted by user.", flush=True)
            if process and process.poll() is None:
                process.terminate()
                process.wait()
        except FileNotFoundError:
            print("Error: 'ros2' command not found. Is ROS2 installed and sourced?", flush=True)
        except Exception as e:
            print(f"An unexpected error occurred: {e}", flush=True)
        finally:
            if process and process.poll() is None:
                process.terminate()
                process.wait()

    def launch_ros2_b(self, package_name, launch_name):
        try:
            command = ["ros2", "launch", package_name, launch_name]
            env = self._get_ros2_env()
            subprocess.Popen(command, env=env)
            print(f"Running ROS2 launch: {launch_name} from package: {package_name}")
        except FileNotFoundError:
            print("Error: 'ros2' command not found. Is ROS2 installed and sourced?", flush=True)
        except Exception as e:
            print(f"An unexpected error occurred in launch_ros2_b: {e}", flush=True)
            traceback.print_exc()

    #Python3.8環境を持ち込まないため
    def _get_ros2_env(self):
        env = os.environ.copy()

        # Wasanbon-Web の Python3.8 仮想環境を ROS2 側へ引き継がない
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)

        # pyenv は system Python を使用
        env["PYENV_VERSION"] = "system"

        # venv / pyenv を PATH から除外
        path_list = []
        for path in env.get("PATH", "").split(":"):
            if not path:
                continue
            if ".venv/bin" in path:
                continue
            if "/.pyenv/" in path:
                continue
            path_list.append(path)

        # ROS2 Humble / system Python を優先
        env["PATH"] = ":".join(
            ["/opt/ros/humble/bin", "/usr/bin", "/bin"] + path_list
        )

        return env

    @manifest
    def install(self, args):
        """ Install RTCs to System
        $ ./mgr.py system install <all or RTC_NAME>
        """
        self.parser.add_option('-f', '--force', help='Force option (default=True)', default=True, action='store_true', dest='force_flag')
        self.parser.add_option('-s', '--standalone', help='Install Standalone RTC(default=False)',
                               default=False, action='store_true', dest='standalone_flag')
        self.parser.add_option('-d', '--duplicate', help='Allow Duplicate RTC Creation(default=False)',
                               default=False, action='store_true', dest='allow_duplicate')
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag
        force = options.force_flag
        standalone = options.standalone_flag
        allow_duplicate = options.allow_duplicate
        wasanbon.arg_check(argv, 4)

        pack = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        if argv[3] == 'all':
            rtcs = admin.rtc.get_rtcs_from_package(pack, verbose=verbose)
        else:
            rtcs = [admin.rtc.get_rtc_from_package(pack, arg, verbose=verbose) for arg in argv[3:]]

        retval = 0
        for rtc in rtcs:
            ret = admin.systeminstaller.install_rtc_in_package(pack, rtc, verbose=verbose,
                                                               preload=True,
                                                               precreate=True,
                                                               copy_conf=True,
                                                               rtcconf_filename="",
                                                               copy_bin=True,
                                                               standalone=standalone,
                                                               conffile=None,
                                                               allow_duplication=allow_duplicate)

            if ret != 0:
                retval = ret

        return retval

    @manifest
    def uninstall(self, args):
        """ Uninstall RTC from system.
        $ ./mgr.py system uninstall <RTC_NAME>
        """
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag

        wasanbon.arg_check(argv, 4)

        pack = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        rtcs = [admin.rtc.get_rtc_from_package(pack, arg, verbose=verbose) for arg in argv[3:]]
        retval = 0
        for rtc in rtcs:
            ret = admin.systeminstaller.uninstall_rtc_from_package(pack, rtc, verbose=verbose)

            if ret != 0:
                retval = ret
        return retval

    @manifest
    def is_running(self, args):
        """ Check System is running or not. This command will output True or False on console.
        $ ./mgr.py system is_running
        """
        options, argv = self.parse_args(args[:])
        verbose = options.verbose_flag

        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        print(admin.systemlauncher.is_launched(package))

        return 0

    @manifest
    def terminate(self, args):
        """ Terminate Launched System.
        $ ./mgr.py system terminate
        """
        options, _ = self.parse_args(args[:])
        verbose = options.verbose_flag
        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)

        retval = 0
        try:
            admin.systembuilder.deactivate_system(package, verbose=verbose)
        except wasanbon.BuildSystemException:
            sys.stdout.write('# Build System Failed.\n')
            traceback.print_exc()
            retval = -1
        except Exception:
            traceback.print_exc()
            retval = -1
        finally:
            try:
                admin.systemlauncher.exit_all_rtcs(package, verbose=verbose)
                admin.systemlauncher.terminate_system(package, verbose=verbose)
            except Exception:
                traceback.print_exc()
                retval = -1
        return retval

    @manifest
    def build(self, args):
        """ Build System in Console interactively
        $ ./mgr.py system build
        """
        self.parser.add_option('-b', '--background', help='Launch in background(default=False)',
                               default=False, action='store_true', dest='background_flag')
        self.parser.add_option('-w', '--wakeuptimeout', help='Timeout of Sleep Function when waiting for the wakeup of RTC-Daemons',
                               default=5, dest='wakeuptimeout', action='store', type='float')
        options, _ = self.parse_args(args[:])
        verbose = options.verbose_flag
        background = options.background_flag
        wakeuptimeout = options.wakeuptimeout

        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        global endflag
        endflag = False
        retval = 0

        try:
            processes = admin.systemlauncher.launch_system(package, verbose=verbose)
            time.sleep(wakeuptimeout)

            package = admin.package.get_package_from_path(os.getcwd())
            nss = admin.nameserver.get_nameservers_from_package(package, verbose=verbose)

            for ns in nss:
                ns.refresh(verbose=verbose)
            # Interactive Connect
            pairs = admin.systemeditor.get_connectable_pairs(nss, verbose=verbose)
            from wasanbon import util
            for pair in pairs:
                if util.no_yes('# Connect? (%s->%s)\n' % (admin.systembuilder.get_port_full_path(pair[0]),
                                                          admin.systembuilder.get_port_full_path(pair[1]))) == 'yes':
                    while True:
                        try:
                            admin.systembuilder.connect_ports(pair[0], pair[1], verbose=verbose)
                            sys.stdout.write('## Connected.\n')
                            break
                        except Exception:
                            if verbose:
                                traceback.print_exc()
                                pass
                            sys.stdout.write('## Failed. \n')
                            if util.yes_no('### Retry?') == 'no':
                                break
                pass

            rtc_names = []
            rtcs = []
            for ns in nss:
                rtc_names = rtc_names + [admin.systembuilder.get_component_full_path(rtc) for rtc in ns.rtcs]
                rtcs = rtcs + ns.rtcs

            # Interactive Configure
            def select_rtc(ans):
                confs = admin.systemeditor.get_active_configuration_data(rtcs[ans])
                conf_names = [conf.name + ':' + conf.data for conf in confs]

                def select_conf(ans2):
                    key = confs[ans2].name
                    sys.stdout.write(' INPUT (%s):' % key)
                    val = input()
                    if util.yes_no('%s = %s. Okay?' % (key, val)) == 'yes':
                        admin.systembuilder.set_active_configuration_data(rtcs[ans], key, val)
                        return True
                    return False
                util.choice(conf_names, select_conf, msg='Select Configuration')
                return False
            util.choice(rtc_names, select_rtc, msg='Select RTC')

            # Save Running System
            if util.yes_no('# Save System ?') == 'yes':
                filename = os.path.basename(package.default_system_filepath)
                while True:
                    if util.yes_no('# Rename filename? (default:%s)' % filename) == 'yes':
                        while True:
                            sys.stdout.write('# Input:')
                            val = input()
                            if util.yes_no('# New Filename = %s. Okay?' % val) == 'yes':
                                filename = val
                                break
                            pass
                        pass
                    # File check
                    filepath = os.path.join(package.get_systempath(fullpath=True), filename)
                    sys.stdout.write('## Saving to %s\n' % filepath)
                    if os.path.isfile(filepath):
                        if util.yes_no('## Overwrite?') == 'yes':
                            newfilename = filepath + wasanbon.timestampstr()
                            sys.stdout.write('## Rename existing file to %s\n' % os.path.basename(newfilename))
                            os.rename(filepath, newfilename)
                            break
                    else:
                        break

                while True:
                    sys.stdout.write('# Input Vendor Name:')
                    vendorName = input()
                    sys.stdout.write('# Input Version:')
                    version = input()
                    sys.stdout.write('# Input System Name (%s):' % package.name)
                    systemName = input()
                    if len(systemName) == 0:
                        systemName = package.name
                    sys.stdout.write('# Input Description of System (abstract):')
                    abstract = input()

                    sys.stdout.write('## Vendor Name = %s\n' % vendorName)
                    sys.stdout.write('## Version     = %s\n' % version)
                    sys.stdout.write('## System Name = %s\n' % systemName)
                    sys.stdout.write('## Abstract    = %s\n' % abstract)
                    if util.yes_no('# Okay?') == 'yes':
                        break
                    else:
                        sys.stdout.write('# Retry')

                for i in range(5):
                    try:
                        sys.stdout.write('# Saving to %s\n' % filepath)
                        admin.systemeditor.save_to_file(nss, filepath,
                                                        system_name=systemName,
                                                        abstract=abstract,
                                                        version=version,
                                                        vendor=vendorName,
                                                        verbose=verbose)
                        break
                    except Exception:
                        traceback.print_exc()
                        time.sleep(1.0)
                        pass
                pass
            else:
                sys.stdout.write('## Aborted.')

        except wasanbon.BuildSystemException:
            sys.stdout.write('# Build System Failed.\n')
            traceback.print_exc()
            retval = -1
        except Exception:
            traceback.print_exc()
            retval = -1
        finally:
            try:
                admin.systemlauncher.exit_all_rtcs(package, verbose=verbose)
                admin.systemlauncher.terminate_system(package, verbose=verbose)
            except Exception:
                traceback.print_exc()
                retval = -1
        return retval

    @manifest
    def configure(self, args):
        """ Configure system interactively in console.
        $ ./mgr.py system configure
        """
        self.parser.add_option('-f', '--file', help='Configure with Specific RTSProfile (must be placed in system_dir',
                               default=None, dest='systemfile', action='store', type='string')
        options, _ = self.parse_args(args[:])
        verbose = options.verbose_flag
        package = admin.package.get_package_from_path(os.getcwd())
        if options.systemfile:
            filename = os.path.join(package.get_systempath(), options.systemfile)
        else:
            filename = package.default_system_filepath
        from rtsprofile.rts_profile import RtsProfile
        file = open(filename, 'r')
        rtsprofile = RtsProfile(xml_spec=file)
        del(file)
        rtc_names = [rtc.instance_name for rtc in rtsprofile.components]

        from wasanbon import util

        def select_rtc(ans):
            rtc = rtsprofile.components[ans]
            confs = []
            active_conf_index = -1
            if len(rtc.configuration_sets) != 0:
                for i, conf in enumerate(rtc.configuration_sets):
                    if conf.id == rtc.active_configuration_set:
                        active_conf_index = i
                        confs = conf.configuration_data
            conf_names = [conf.name + ':' + conf.data for conf in confs]

            def select_conf(ans2):
                key = confs[ans2].name
                sys.stdout.write('## INPUT (%s):' % key)
                val = input()
                if util.yes_no('# %s = %s. Okay?' % (key, val)) == 'yes':
                    rtc.configuration_sets[active_conf_index].configuration_data[ans2].data = val
                    return True
                return False
            util.choice(conf_names, select_conf, msg='# Select Configuration')
            return False

        util.choice(rtc_names, select_rtc, msg='# Select RTC')

        if util.yes_no("Save System?") != 'yes':
            sys.stdout.write('# Aborted \n')
            return 0
        while True:
            if util.no_yes('Rename Filename?') == 'yes':
                filepath = os.path.join(package.get_systempath(), input('Filename:'))
            else:
                filepath = filename
                newfile = filepath + wasanbon.timestampstr()
                try:
                    os.rename(filepath, newfile)
                except Exception as e:
                    sys.stdout.write('## Exception occurred when renaming file.\n')
                    traceback.print_exc()
                    continue
            try:
                fout = open(filepath, 'w')
                fout.write(rtsprofile.save_to_xml())
                fout.close()
            except Exception:
                sys.stdout.write('## Exception occurred when saving file.\n')
                traceback.print_exc()
                continue
            break
        return 0

    @manifest
    def switch(self, args):
        """ Switch RT-System. The SYSTEM_FILENAME file must be included in RTS_DIR (defined in setting.yaml)
        $ ./mgr.py system switch [SYSTEM_FILENAME]
        """
        options, argv = self.parse_args(args[:])
        verbose = options.verbose_flag

        package = admin.package.get_package_from_path(os.getcwd())
        filenames = [file for file in os.listdir(package.get_systempath()) if file.endswith('.xml')]

        opt_filename = ''
        if len(argv) > 3:
            opt_filename = argv[3]

        def filter_func(ans):
            file = filenames[ans]
            import yaml
            dict = yaml.safe_load(open(package.setting_file_path, 'r'))
            setting_file_path = package.setting_file_path
            archive_path = os.path.join(package.path, 'backup')
            if not os.path.isdir(archive_path):
                os.mkdir(archive_path)
            archived_file_path = os.path.join(archive_path, 'setting.yaml' + wasanbon.timestampstr())
            os.rename(setting_file_path, archived_file_path)
            dict['application']['system'] = file
            yaml_dump = yaml.dump(dict, encoding='utf8', allow_unicode=True, default_flow_style=False).decode('utf-8')
            open(setting_file_path, 'w').write(yaml_dump)
            return False

        if opt_filename in filenames:
            index = filenames.index(opt_filename)
            sys.stdout.write('# Select System File is (%s).\n' % opt_filename)
            filter_func(index)
        else:
            from wasanbon import util
            util.choice(filenames, filter_func, msg='# Select System File')
        return 0

    @manifest
    def list(self, args):
        """ List Systems installed.
        $ ./mgr.py system list
        """
        self.parser.add_option('-l', '--long', help='Long Format (default=False)', default=False, action='store_true', dest='long_flag')
        options, _ = self.parse_args(args[:])
        verbose = options.verbose_flag
        long = options.long_flag

        package = admin.package.get_package_from_path(os.getcwd())
        filenames = [file for file in os.listdir(package.get_systempath()) if file.endswith('.xml') and not file.startswith('.')]

        defaultSystemPath = package.default_system_filepath
        for file in filenames:
            path = os.path.join(package.get_systempath(), file)
            if not long:
                sys.stdout.write('- %s\n' % file)
            else:
                from rtsprofile import rts_profile
                try:
                    rtsp = rts_profile.RtsProfile(open(os.path.join(package.get_systempath(), file), 'r'))
                except Exception:
                    sys.stdout.write('%s : \n' % file)
                    sys.stdout.write('  status : error\n')
                    if verbose:
                        traceback.print_exc()
                    continue
                sys.stdout.write('%s : \n' % file)
                sys.stdout.write('  default  : %s\n' % str(defaultSystemPath == path))
                sys.stdout.write('  status   : success\n')
                sys.stdout.write('  id       : %s\n' % rtsp.id)
                sys.stdout.write('  abstract : %s\n' % rtsp.abstract)
                if len(rtsp.components) > 0:
                    sys.stdout.write('  components:\n')
                    for comp in rtsp.components:
                        sys.stdout.write('    %s : \n' % comp.instance_name)
                        sys.stdout.write('      id                       : %s\n' % comp.id)
                        sys.stdout.write('      path_uri                 : %s\n' % comp.path_uri)
                        sys.stdout.write('      is_required              : %s\n' % comp.is_required)
                        sys.stdout.write('      active_configuration_set : %s\n' % comp.active_configuration_set)
                        if len(comp.configuration_sets) > 0:
                            sys.stdout.write('      configurations_sets :\n')
                            for conf_set in comp.configuration_sets:
                                sys.stdout.write('        %s : \n' % conf_set.id)
                                for conf in conf_set.configuration_data:
                                    sys.stdout.write('          %s : %s\n' % (conf.name, conf.data))
        return 0

    @manifest
    def list_rtc(self, args):
        """ List RTCs installed.
        $ ./mgr.py system list_rtc
        """
        options, _ = self.parse_args(args[:])
        verbose = options.verbose_flag

        package = admin.package.get_package_from_path(os.getcwd())
        rtcconf_paths = package.rtcconf
        for language, rtcconf_path in list(rtcconf_paths.items()):
            rtcconf = admin.rtcconf.RTCConf(rtcconf_path)
            sys.stdout.write('%s :\n' % language)
            sys.stdout.write('  conf_file : %s\n' % rtcconf_path)
            sys.stdout.write('  rtcd :\n')
            sys.stdout.write('    uri            : %s\n' % rtcconf['corba.master_manager'])
            sys.stdout.write('    nameservers    : %s\n' % rtcconf['corba.nameservers'])
            sys.stdout.write('    installed_rtcs : %s\n' % rtcconf['manager.components.precreate'])
        return 0

    @manifest
    def dump(self, args):
        """ Dump RTSProfile to STDOUT.
        $ ./mgr.py system dump
        """
        self.parser.add_option('-f', '--file', help='Build System with Specific RTSProfile (must be placed in system_dir',
                               default=None, dest='systemfile', action='store', type='string')
        options, _ = self.parse_args(args[:])
        systemfile = options.systemfile
        verbose = options.verbose_flag
        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)

        if systemfile is None:
            systemfile = package.default_system_filepath
        else:
            systemfile = os.path.join(package.get_systempath(), systemfile)

        if not os.path.isfile(systemfile):
            print('# File Not Found.')
            return -1

        for line in open(systemfile, 'r'):
            sys.stdout.write(line)
        return 0

    @manifest
    def cat(self, args):
        """ Cat input data to RTSProfile(DefaultSystem.xml).
        $ ./mgr.py system cat <INPUT_DATA>
        """
        self.parser.add_option('-f', '--file', help='Build System with Specific RTSProfile (must be placed in system_dir',
                               default=None, dest='systemfile', action='store', type='string')
        options, argv = self.parse_args(args[:])
        verbose = options.verbose_flag
        systemfile = options.systemfile

        wasanbon.arg_check(argv, 4)
        sys.stdout.write('## Input Data is %s\n' % argv[3])

        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        if systemfile is None:
            systemfile = package.default_system_filepath
        else:
            systemfile = os.path.join(package.get_systempath(), systemfile)

        from wasanbon import util
        if util.yes_no(('## Write Input Data to {}?').format(systemfile)) == 'no':
            sys.stdout.write('## Aborted.\n')
            return 0

        if os.path.isfile(systemfile):
            newfile = systemfile + wasanbon.timestampstr()
            os.rename(systemfile, newfile)

        fout = open(systemfile, 'w')
        fout.write(argv[3])
        fout.close()

        sys.stdout.write('Success\n')
        return 0

    @manifest
    def copy(self, args):
        """ Copy RTSProfile(DefaultSystem.xml).
        $ ./mgr.py system copy <SOURCE_RTSP_FILE> <DEST_RTSP_FILE>
        """
        self.parser.add_option('-f', '--force', help='Force Delete without yes/no option (default=False)',
                               default=False, dest='force_flag', action='store_true')
        options, argv = self.parse_args(args[:])
        verbose = options.verbose_flag
        force = options.force_flag

        wasanbon.arg_check(argv, 5)

        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        srcfile = argv[3]
        dstfile = argv[4]
        srcfile_relpath = os.path.join(package.get_systempath(fullpath=False), srcfile)
        srcfile_fullpath = os.path.join(package.get_systempath(), srcfile)
        if not os.path.isfile(srcfile_fullpath):
            sys.stdout.write('## No System File exists.\n')
            return -1

        dstfile_relpath = os.path.join(package.get_systempath(fullpath=False), dstfile)
        dstfile_fullpath = os.path.join(package.get_systempath(), dstfile)
        if os.path.isfile(dstfile_fullpath):
            if not force:
                from wasanbon import util
                if util.no_yes('# Overwrite? (%s):' % dstfile_relpath) == 'no':
                    sys.stdout.write('## Aborted.\n')
                    return 0
            newfile = dstfile_fullpath + wasanbon.timestampstr()
            os.rename(dstfile_fullpath, newfile)

        import shutil
        shutil.copyfile(srcfile_fullpath, dstfile_fullpath)
        sys.stdout.write('## Success\n')
        return 0

    @manifest
    def delete(self, args):
        """ Delete RTSProfile(DefaultSystem.xml).
        $ ./mgr.py system delete <SYSTEM_FILENAME>
        """
        self.parser.add_option('-f', '--force', help='Force Delete without yes/no option (default=False)',
                               default=False, dest='force_flag', action='store_true')
        options, argv = self.parse_args(args[:])
        verbose = options.verbose_flag
        force = options.force_flag

        wasanbon.arg_check(argv, 4)

        print("DEBUG: before get_package_from_path", flush=True)
        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        print("DEBUG: after get_package_from_path", flush=True)

        systemfile = argv[3]
        systemfile_relpath = os.path.join(package.get_systempath(fullpath=False), systemfile)
        systemfile_fullpath = os.path.join(package.get_systempath(), systemfile)
        if not os.path.isfile(systemfile_fullpath):
            sys.stdout.write('## No System File exists.\n')
            return -1

        if not force:
            from wasanbon import util
            if util.no_yes('# Delete? (%s):' % systemfile_relpath) == 'no':
                sys.stdout.write('## Aborted.\n')
                return 0

        newfile = systemfile_fullpath + wasanbon.timestampstr()
        os.rename(systemfile_fullpath, newfile)

        sys.stdout.write('## Success\n')
        return 0