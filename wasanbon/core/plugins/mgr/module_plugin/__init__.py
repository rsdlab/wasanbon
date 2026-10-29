import os
import sys
import signal
import time
import traceback
import threading
import wasanbon
from wasanbon.core.plugins import PluginFunction, manifest
from wasanbon.core.plugins.admin.rtc_plugin import RTCPackage

import xml.etree.ElementTree as ET
import subprocess

ev = threading.Event()
endflag = False


class Plugin(PluginFunction):
    """ RT-Component in Package management Plugin. """

    def __init__(self):
        super(Plugin, self).__init__()
        pass

    def depends(self):
        return ['admin.environment',
                'admin.package',
                'admin.rtc',
                'admin.rtcconf',
                'admin.rtcprofile',
                'admin.builder',
                'admin.systeminstaller',
                'admin.systemlauncher',
                'admin.editor']

    def _print_rtcs(self, args):
        pack = admin.package.get_package_from_path(os.getcwd())
        rtcs = admin.rtc.get_rtcs_from_package(pack)
        for r in rtcs:
            print(r.rtcprofile.basicInfo.name)

    @manifest
    def middleware(self, args):
        # print("middleware")
        verbose = False
        package = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)

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
        ros_version = None
        package_xml_dirs = self.find_package_xml(
            os.path.dirname(package.get_rtcpath()),
            'package.xml'
        )

        if package_xml_dirs:
            file_path = f"{package_xml_dirs[0]}/package.xml"
            ros_version = self.get_ros_version(file_path)

        if self.rtc_check == "ok":
            print("rtm")
        elif ros_version is not None:
            print(f"ros{ros_version}")

    @manifest
    def _test___(self, args):
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag

        wasanbon.arg_check(argv, 4)
        pack = admin.package.get_package_from_path(os.getcwd())
        ##roscore確認
        check_roscore=self.is_roscore_running()
        if str(self.is_roscore_running()) == "False":
            ##roscore
            self.start_roscore()
        ##chmod +x
        directory = f"{os.path.dirname(pack.get_rtcpath())}/src"  # 対象のディレクトリを指定
        self.add_execute_permission(directory)
        ##rosrun
        self.run_ros_node(pack.name, argv[3])

    def is_roscore_running(self):
        try:
            # rosnode list コマンドを実行
            result = subprocess.run(
                ["rosnode", "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # 成功時（roscoreが動作中）
            if result.returncode == 0:
                print("roscore is running.")
                return True
            else:
                print("roscore is NOT running.")
                print(result.stderr)
                return False

        except FileNotFoundError:
            print("Error: 'rosnode' command not found. Is ROS installed and sourced?")
            return False
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False

    def start_roscore(self):
        try:
            process = subprocess.Popen(
                ["roscore"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 一定時間待機してロスコアが起動したか確認
            time.sleep(3)

        except FileNotFoundError:
            print("Error: 'roscore' command not found. Make sure ROS is installed and sourced.")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None

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
                # エラーが発生した場合
                print(f"Error while adding execute permission:\n{result.stderr}")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    def _read_stream(self, stream, prefix=""):
        """Helper function to read from a stream and print lines."""
        try:
            for line in iter(stream.readline, ''):
                print(f"{prefix}{line}", end="", flush=True)
        except Exception as e:
            pass
        finally:
            if hasattr(stream, 'close') and not stream.closed:
                stream.close()

    def run_ros_node(self, package_name, node_name):
        process = None
        try:
            # rosrunコマンドの実行
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            command = ["rosrun", package_name, node_name]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 親プロセス側のパイプ読み取りバッファ設定
                env=env     # サブプロセスに環境変数を渡す
            )

            print(f"Running ROS node: {node_name} from package: {package_name}", flush=True)

            # 標準出力と標準エラーを読み取るためのスレッドを作成
            stdout_thread = threading.Thread(target=self._read_stream, args=(process.stdout,))
            stderr_thread = threading.Thread(target=self._read_stream, args=(process.stderr,))

            # デーモンスレッドに設定 (メインスレッド終了時に自動終了)
            stdout_thread.daemon = True
            stderr_thread.daemon = True

            stdout_thread.start()
            stderr_thread.start()

            # プロセスが終了するのを待つ (KeyboardInterruptをメインスレッドで受け付けるためループ)
            while process.poll() is None:
                try:
                    time.sleep(0.1)
                except KeyboardInterrupt:
                    # KeyboardInterruptを再送出し、メインの例外ハンドラで処理
                    raise

            # スレッドが残りの出力を処理するのを待つ (タイムアウト付き)
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

        except KeyboardInterrupt:
            print("\nNode execution interrupted by user.", flush=True)
            # process変数がNoneでないこと、かつプロセスがまだ実行中であることを確認
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)  # 終了を待機 (タイムアウト付き)
                except subprocess.TimeoutExpired:
                    process.kill() # 強制終了
                    process.wait() # 念のため待機
        except FileNotFoundError:
            print("Error: 'rosrun' command not found. Is ROS installed and sourced?", flush=True)
        except Exception as e:
            print(f"An unexpected error occurred in run_ros_node: {e}", flush=True)
            traceback.print_exc() # 詳細なエラー情報を表示
        finally:
            # プロセスがまだ動作中の場合は確実に終了させる
            if process and process.poll() is None:
                print(f"Terminating node {node_name} in finally block.", flush=True)
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            # print(f"Node {node_name} execution finished or was terminated.", flush=True) # デバッグ用

    def run_ros_node_b(self, package_name, node_name):
        try:
            command = ["rosrun", package_name, node_name]

            # ノードを非同期で起動（出力は捨ててもよいなら stdout/stderr を DEVNULL に）
            subprocess.Popen(
                command,
                stdout=subprocess.PIPE,  # または subprocess.DEVNULL
                stderr=subprocess.PIPE,
                text=True,
            )

            print(f"Running ROS node: {node_name} from package: {package_name}", flush=True)

        except FileNotFoundError:
            print("Error: 'rosrun' command not found. Is ROS installed and sourced?", flush=True)
        except Exception as e:
            print(f"An unexpected error occurred in run_ros_node_b: {e}", flush=True)
            traceback.print_exc()

    def run_ros2_node(self, package_name, node_name):
        process = None
        try:
            env = self._get_ros2_env()
            env["PYTHONUNBUFFERED"] = "1"

            command = ["ros2", "run", package_name, node_name]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )

            print(
                f"Running ROS2 node: {node_name} from package: {package_name}",
                flush=True
            )

            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(process.stdout,)
            )
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(process.stderr,)
            )

            stdout_thread.daemon = True
            stderr_thread.daemon = True

            stdout_thread.start()
            stderr_thread.start()

            while process.poll() is None:
                try:
                    time.sleep(0.1)
                except KeyboardInterrupt:
                    raise

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

        except KeyboardInterrupt:
            print("\nNode execution interrupted by user.", flush=True)
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        except FileNotFoundError:
            print(
                "Error: 'ros2' command not found. Is ROS2 installed and sourced?",
                flush=True
            )

        except Exception as e:
            print(
                f"An unexpected error occurred in run_ros2_node: {e}",
                flush=True
            )
            traceback.print_exc()

        finally:
            if process and process.poll() is None:
                print(
                    f"Terminating node {node_name} in finally block.",
                    flush=True
                )
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def run_ros2_node_b(self, package_name, node_name):
        try:
            env = self._get_ros2_env()

            command = ["ros2", "run", package_name, node_name]

            subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            print(
                f"Running ROS2 node: {node_name} from package: {package_name}",
                flush=True
            )

        except FileNotFoundError:
            print(
                "Error: 'ros2' command not found. Is ROS2 installed and sourced?",
                flush=True
            )

        except Exception as e:
            print(
                f"An unexpected error occurred in run_ros2_node_b: {e}",
                flush=True
            )
            traceback.print_exc()

    #Python3.8環境を持ち込まないため
    def _get_ros2_env(self):
        env = os.environ.copy()

        # Wasanbon-Web の Python3.8 仮想環境を ROS2 子プロセスへ引き継がない
        env.pop("VIRTUAL_ENV", None)

        # pyenv も system Python を使わせる
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
    def build(self, args):
        """ Build component in current Package.
        $ ./mgr.py module build
        """
        ##RTC_CHECK
        self.parser.add_option('-o', '--only', help='Build Only (Not Install) (default=False)', default=False, action='store_true', dest='only_flag')
        self.parser.add_option('-s', '--standalone', help='Install Standalone Mode (default=False)',
                               default=False, action='store_true', dest='standalone_flag')
        options, argv = self.parse_args(args, self._print_rtcs)
        verbose = options.verbose_flag
        if sys.platform == 'win32':
            if verbose:
                sys.stdout.write('# In Windows, always build with verbose option.\n')
            verbose = True
        only = options.only_flag
        standalone = options.standalone_flag

        pack = admin.package.get_package_from_path(os.getcwd())
        rtcs = admin.rtc.get_rtcs_from_package(pack, verbose=verbose)

        self.rtc_check="no"
        if rtcs:
            for rtc in rtcs:
                xml_path=os.path.join(pack.get_rtcpath(),rtc.rtcprofile.basicInfo.name,"RTC.xml")
                # print(rtc.rtcprofile.basicInfo.name)
                # print(pack.get_rtcpath())
                if os.path.isfile(xml_path):
                    self.rtc_check="ok"
                else:
                    self.rtc_check="no"


        return_value_map = {}
        retval = 0

        ##ROS_CHECK
        ros_version = None
        package_xml_dirs = self.find_package_xml(os.path.dirname(pack.get_rtcpath()),'package.xml')
        if package_xml_dirs:
            file_path = f"{package_xml_dirs[0]}/package.xml"
            ros_version = self.get_ros_version(file_path)

        ##BUILD_START
        if self.rtc_check=="ok":
            for rtc in rtcs:
                sys.stdout.write('# Building RTC (%s)\n' % rtc.rtcprofile.basicInfo.name)
                ret, msg = admin.builder.build_rtc(rtc.rtcprofile, verbose=verbose)
                return_value_map[rtc.rtcprofile.basicInfo.name] = ret
                if not ret:
                    sys.stdout.write('## Failed.\n')
                    retval = -1
                else:
                    sys.stdout.write('## Success.\n')
                    if not only:
                        if not standalone:
                            # Confirm if this rtc is
                            standalone_flag = admin.systeminstaller.is_installed(pack, rtc, verbose=verbose, standalone=True)
                        else:
                            standalone_flag = standalone
                        sys.stdout.write('## Installing RTC (standalone=%s).\n' % (standalone_flag is True))
                        admin.systeminstaller.install_rtc_in_package(pack, rtc, verbose=verbose, standalone=standalone_flag)
                        sys.stdout.write('### Success.\n')
        elif ros_version == 1:
            ##catkin build
            last_parts = [os.path.basename(path) for path in package_xml_dirs]
            workspace_path = self.find_package_workspace(pack.name)
            self.run_catkin_build(workspace_path, last_parts)

        elif ros_version == 2:
            package_names = [os.path.basename(path) for path in package_xml_dirs]
            package_path = package_xml_dirs[0]
            workspace_path = self.find_colcon_workspace(package_path)
            self.run_colcon_build(workspace_path, package_names)
        else:
            sys.stdout.write('## Not found Package\n')

        if verbose:
            sys.stdout.write('Build Summary:\n')
            for key, value in list(return_value_map.items()):
                sys.stdout.write(' - Build RTC (' + key + ')' + ' ' * (25 - len(key)) + ('Success' if value else 'False') + '\n')
        return retval

    def find_package_workspace(self,package_name):
        ros_package_paths = os.environ.get("ROS_PACKAGE_PATH", "").split(":")
        # print(ros_package_paths)
        found = False

        for path in ros_package_paths:
            # 末尾のディレクトリ名と一致する場合
            if os.path.basename(path) == package_name:
                workspace = path.split("/src/")[0]
                return workspace

            # 深い階層にあるディレクトリを探索
            elif os.path.isdir(path):
                candidate = os.path.join(path, package_name)
                if os.path.exists(candidate):
                    workspace = candidate.split("/src/")[0]
                    return workspace

        return None

    def find_colcon_workspace(self, package_path):
        current = os.path.abspath(package_path)

        while True:
            parent = os.path.dirname(current)

            if os.path.basename(current) == "src":
                return parent

            if parent == current:
                return None

            current = parent

    def find_package_xml(self, directory, object):
        package_dirs = []
        for root, dirs, files in os.walk(directory):
            if object in files:
                package_dirs.append(root)
        return package_dirs

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

    def run_catkin_build(self, workspace_path, package_names):
        try:
            command = ["catkin", "build"] + package_names

            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 標準出力とエラーをリアルタイムで読み取る
            for line in process.stdout:
                print(line, end="")

            # プロセスが終了するまで待機
            process.wait()

            # プロセスの終了コードをチェック
            if process.returncode == 0:
                print("\ncatkin build completed successfully.")
            else:
                print("\ncatkin build failed.")
                # 標準エラーをすべて出力
                for line in process.stderr:
                    print(line, end="")

        except FileNotFoundError:
            print("Error: 'catkin' command not found. Make sure ROS is properly installed and sourced.")
        except Exception as e:
            print(f"An error occurred: {e}")

    def run_colcon_build(self, workspace_path, package_names):
        try:
            command = ["colcon", "build", "--packages-select"] + package_names

            process = subprocess.Popen(
                command,
                cwd=workspace_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            for line in process.stdout:
                print(line, end="")

            process.wait()

            if process.returncode == 0:
                print("\ncolcon build completed successfully.")
            else:
                print("\ncolcon build failed.")
                for line in process.stderr:
                    print(line, end="")

        except FileNotFoundError:
            print("Error: 'colcon' command not found. Make sure ROS2 is properly installed and sourced.")
        except Exception as e:
            print(f"An error occurred: {e}")

    @manifest
    def list(self, args):
        """ List RTC in current Package.
        $ ./mgr.py rtc list
        """
        self.parser.add_option('-l', '--long', help='Long Format (default=False)', default=False, action='store_true', dest='long_flag')
        self.parser.add_option('-d', '--detail', help='Long Format (default=False)', default=False, action='store_true', dest='detail_flag')
        options, argv = self.parse_args(args)
        verbose = options.verbose_flag
        long = options.long_flag
        detail = options.detail_flag
        if detail:
            long = True

        pack = admin.package.get_package_from_path(os.getcwd())

        rtcs = admin.rtc.get_rtcs_from_package(pack, verbose=verbose)
        for r in rtcs:
            if not long:
                print(' - ' + r.rtcprofile.basicInfo.name)
            elif long:
                print(r.rtcprofile.basicInfo.name + ' : ')
                print('  basicInfo : ')
                print('    description : ' + r.rtcprofile.basicInfo.description)
                print('    category    : ' + r.rtcprofile.basicInfo.category)
                print('    vendor      : ' + r.rtcprofile.basicInfo.vendor)
                if len(r.rtcprofile.dataports):
                    print('  dataports : ')
                    for d in r.rtcprofile.dataports:
                        if not detail:
                            print('     - ' + d.name)
                        else:
                            print('    ' + d.name + ':')
                            print('      portType : ' + d.portType)
                            print('      type     : ' + d.type)
                if len(r.rtcprofile.serviceports):
                    print('  serviceports :')
                    for s in r.rtcprofile.serviceports:
                        if not detail:
                            print('     - ' + s.name)
                        else:
                            print('    ' + s.name + ':')
                            for i in s.serviceInterfaces:
                                print('      ' + i.name + ':')
                                print('        type         : ' + i.type)
                                print('        instanceName : ' + i.instanceName)
            if detail:
                print('  language : ')
                print('    kind        : ' + r.rtcprofile.language.kind)
            if long or detail:
                print('')
        return 0


    @manifest
    def clean(self, args):
        """ Clean RTC in current Package.
        $ ./mgr.py rtc clean <all or RTC_NAME>
        """
        options, argv = self.parse_args(args, self._print_rtcs)
        verbose = options.verbose_flag

        if verbose:
            sys.stdout.write('# Cleanup RTCs\n')

        wasanbon.arg_check(argv, 4)
        pack = admin.package.get_package_from_path(os.getcwd(), verbose=verbose)
        if argv[3] == 'all':
            rtcs = admin.rtc.get_rtcs_from_package(pack, verbose=verbose)
        else:
            rtcs = [admin.rtc.get_rtc_from_package(pack, argv[3], verbose=verbose)]

        retval = 0
        for rtc in rtcs:
            if verbose:
                sys.stdout.write('# Cleanuping RTC %s\n' % rtc.rtcprofile.basicInfo.name)

            ret, msg = admin.builder.clean_rtc(rtc.rtcprofile, verbose=verbose)
            if not ret:
                retval = -1

        return retval

    @manifest
    def delete(self, args):
        """ Delete RTC from Package
        $ ./mgr.py rtc delete <all or RTC_NAME>
        """
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag

        pack = admin.package.get_package_from_path(os.getcwd())
        if argv[3] == 'all':
            rtcs = admin.rtc.get_rtcs_from_package(pack, verbose=verbose)
        else:
            rtcs = [admin.rtc.get_rtc_from_package(pack, argv[3], verbose=verbose)]
        import shutil
        for rtc in rtcs:
            if os.path.isdir(rtc.path):
                sys.stdout.write('# Deleting RTC (%s)\n' % rtc.rtcprofile.basicInfo.name)

                def remShut(*args):
                    import stat
                    func, path, _ = args
                    os.chmod(path, stat.S_IWRITE)
                    os.remove(path)
                    pass
                shutil.rmtree(rtc.path, onerror=remShut)
        return 0

    @manifest
    def edit(self, args):
        """ Edit RTC with editor.
        $ ./mgr.py rtc edit <RTC_NAME>
        """
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag

        wasanbon.arg_check(argv, 4)

        pack = admin.package.get_package_from_path(os.getcwd())
        rtc = admin.rtc.get_rtc_from_package(pack, argv[3], verbose=verbose)
        admin.editor.edit_rtc(rtc, verbose=verbose)
        return 0

    @manifest
    def run(self, args):
        """ Run just one RTC.
        $ ./mgr.py module run
        """
        self.parser.add_option('-b', '--background', help='Launch in background(default=False)',
                               default=False, action='store_true', dest='background_flag') ##
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag
        background = options.background_flag #3
        wasanbon.arg_check(argv, 4)
        package = admin.package.get_package_from_path(os.getcwd())
        print(package)

        ##RTC_CHECK
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
        package_xml_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), 'package.xml')
        ros_version = None
        if package_xml_dirs:
            file_path = f"{package_xml_dirs[0]}/package.xml"
            ros_version = self.get_ros_version(file_path)

        if ros_version == 1:
            if background:
                ##roscore確認
                check_roscore=str(self.is_roscore_running())
                if check_roscore == "False":
                    ##roscore
                    self.start_roscore()

                node_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".py") #nodeのディレクトリ取得
                node_dirs2 = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".cpp")
                if node_dirs:
                    package_name = os.path.basename(os.path.dirname(node_dirs[0]))  #nodeの上のディレクトリがパッケージ
                    self.add_execute_permission(node_dirs[0])

                    ##xmlからnode名取得
                    profile_path=node_dirs[0]+"/profile"+"/"+argv[3]+".xml"
                    node_name=self.extract_node_name_from_xml(profile_path) or argv[3]

                    ##rosrun
                    print(package_name, flush=True)
                    self.run_ros_node_b(package_name, argv[3] + ".py")

                    ##rosnode list
                    self.check_node_is_running(node_name)
                elif node_dirs2:
                    package_name = os.path.basename(os.path.dirname(node_dirs2[0]))  #nodeの上のディレクトリがパッケージ
                    print(package_name, flush=True)
                    self.run_ros_node_b(package_name, argv[3])
                else:
                    print(f"ROS node '{argv[3]}' not found as .py or .cpp", flush=True)

            else:
                ##roscore確認
                check_roscore=str(self.is_roscore_running())
                if check_roscore == "False":
                    ##roscore
                    self.start_roscore()

                node_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".py") #nodeのディレクトリ取得
                node_dirs2 = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".cpp")
                if node_dirs:
                    package_name = os.path.basename(os.path.dirname(node_dirs[0]))  #nodeの上のディレクトリがパッケージ
                    self.add_execute_permission(node_dirs[0])

                    ##rosrun
                    print(package_name, flush=True)
                    self.run_ros_node(package_name, argv[3] + ".py")
                elif node_dirs2:
                    package_name = os.path.basename(os.path.dirname(node_dirs2[0]))  #nodeの上のディレクトリがパッケージ
                    print(package_name, flush=True)
                    self.run_ros_node(package_name, argv[3])
                else:
                    print(f"ROS node '{argv[3]}' not found as .py or .cpp", flush=True)

        elif ros_version == 2:
            if background:
                node_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".py")
                node_dirs2 = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".cpp")
                if node_dirs:
                    package_name = os.path.basename(os.path.dirname(node_dirs[0]))
                    self.add_execute_permission(node_dirs[0])

                    ##xmlからnode名取得
                    profile_path=node_dirs[0]+"/profile"+"/"+argv[3]+".xml"
                    node_name=self.extract_node_name_from_xml(profile_path) or argv[3]

                    ##ros2 run
                    print(package_name, flush=True)
                    self.run_ros2_node_b(package_name, argv[3] + ".py")

                    ##ros2 node list
                    self.check_ros2_node_is_running(node_name)
                elif node_dirs2:
                    package_name = os.path.basename(os.path.dirname(node_dirs2[0]))
                    print(package_name, flush=True)
                    self.run_ros2_node_b(package_name, argv[3])
                else:
                    print(f"ROS2 node '{argv[3]}' not found as .py or .cpp", flush=True)

            else:
                node_dirs = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".py")
                node_dirs2 = self.find_package_xml(os.path.dirname(package.get_rtcpath()), argv[3] + ".cpp")
                if node_dirs:
                    package_name = os.path.basename(os.path.dirname(node_dirs[0]))
                    self.add_execute_permission(node_dirs[0])

                    ##ros2 run
                    print(package_name, flush=True)
                    self.run_ros2_node(package_name, argv[3] + ".py")
                elif node_dirs2:
                    package_name = os.path.basename(os.path.dirname(node_dirs2[0]))
                    print(package_name, flush=True)
                    self.run_ros2_node(package_name, argv[3])
                else:
                    print(f"ROS2 node '{argv[3]}' not found as .py or .cpp", flush=True)

        if self.rtc_check=="ok":
            if background:
                rtc = admin.rtc.get_rtc_from_package(package, argv[3], verbose=verbose)
                start_check=self.run_rtc_in_package(package, rtc, verbose=verbose, background=True)
                self.activate_rtcs("/localhost")
                return start_check

            else:
                rtc = admin.rtc.get_rtc_from_package(package, argv[3], verbose=verbose)
                return self.run_rtc_in_package(package, rtc, verbose=verbose)

    def activate_rtcs(self, host_path="/localhost"):
        try:
            # rtfindコマンドの実行
            time.sleep(1)
            result = subprocess.run(["rtfind", host_path], capture_output=True, text=True, check=True)
            lines = result.stdout.splitlines()

            if not lines:
                # print("rtfindの出力が空です。RTCの起動は行いません。")
                return

            # .rtc を含む行を抽出
            rtc_paths = [line.strip() for line in lines if line.strip().endswith(".rtc")]

            if not rtc_paths:
                # print(".rtc が含まれるエントリが見つかりません。RTCの起動は行いません。")
                return

            # 各rtcに対して rtact を実行
            for rtc_path in rtc_paths:
                print(f"Activating: {rtc_path}")
                subprocess.run(["rtact", rtc_path], check=True)

            # print("すべてのRTCを起動しました。")

        except subprocess.CalledProcessError as e:
            print(f"コマンドエラー: {e}")
        except Exception as e:
            print(f"予期せぬエラー: {e}")

    def extract_node_name_from_xml(self, file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            # 名前空間の処理
            ns = {'node': 'http://www.example.com/node'}

            # node:BasicInfo タグから node:name を取得
            basic_info = root.find("node:BasicInfo", ns)
            if basic_info is not None:
                node_name = basic_info.attrib.get("{http://www.example.com/node}name")
                if node_name:
                    return node_name

            return None

        except Exception as e:
            return None

    def check_node_is_running(self,node_name, timeout_sec=10):
        """
        最大 timeout_sec 秒間、rosnode list を監視して node_name のノードが現れるか確認

        Args:
            node_name (str): ノード名（例: 'talker'）
            timeout_sec (int): 最大監視時間（秒）

        Returns:
            bool: ノードが見つかれば True、見つからなければ False
        """
        full_name = f"/{node_name}"
        start_time = time.time()

        while time.time() - start_time < timeout_sec:
            try:
                result = subprocess.run(["rosnode", "list"], capture_output=True, text=True)
                running_nodes = result.stdout.splitlines()

                if full_name in running_nodes:
                    return True

            except FileNotFoundError:
                return False
            except Exception as e:
                print(f"エラー: {e}")
                return False

            time.sleep(0.5)  # 少し待ってから再確認（負荷を抑える）


        return False

    def check_ros2_node_is_running(self,node_name, timeout_sec=10):
        """
        最大 timeout_sec 秒間、ros2 node list を監視して node_name のノードが現れるか確認
        """
        full_name = f"/{node_name}"
        start_time = time.time()

        while time.time() - start_time < timeout_sec:
            try:
                result = subprocess.run(["ros2", "node", "list"], capture_output=True, text=True)
                running_nodes = result.stdout.splitlines()

                if full_name in running_nodes:
                    return True

            except FileNotFoundError:
                return False
            except Exception as e:
                print(f"エラー: {e}")
                return False

            time.sleep(0.5)

        return False

    def run_rtc_in_package(self, package, rtc, verbose=False, background=False):
        global endflag
        endflag = False

        def signal_action(num, frame):
            print(' - SIGINT captured')
            ev.set()
            global endflag
            endflag = True
            pass

        signal.signal(signal.SIGINT, signal_action)

        if sys.platform == 'win32':
            sys.stdout.write(' - Escaping SIGBREAK...\n')
            signal.signal(signal.SIGBREAK, signal_action)
            pass

        sys.stdout.write('# Executing RTC %s\n' % rtc.rtcprofile.basicInfo.name)
        rtcconf_path = package.rtcconf[rtc.rtcprofile.language.kind]
        rtcconf = admin.rtcconf.RTCConf(rtcconf_path, verbose=verbose)
        rtc_temp = os.path.join("conf", "rtc_temp.conf")
        if os.path.isfile(rtc_temp):
            os.remove(rtc_temp)
            pass
        rtcconf.sync(verbose=True, outfilename=rtc_temp)
        admin.systeminstaller.uninstall_all_rtc_from_package(package, rtcconf_filename=rtc_temp, verbose=True)
        admin.systeminstaller.install_rtc_in_package(package, rtc, rtcconf_filename=rtc_temp, copy_conf=False)
        try:
            admin.systemlauncher.launch_rtcd(package, rtc.rtcprofile.language.kind, rtcconf=rtc_temp, verbose=True)
            if background:
                return 0
            while not endflag:
                try:
                    time.sleep(0.1)
                except IOError as e:
                    print(e)
                    pass
                pass
            pass
        except:
            traceback.print_exc()
            return -1
        if verbose:
            sys.stdout.write('## Exitting RTC Manager.\n')
        admin.systemlauncher.exit_all_rtcs(package, verbose=verbose)
        admin.systemlauncher.terminate_system(package, verbose=verbose)
        return 0

    def terminate_rtcd(self, package, verbose=False):
        if verbose:
            sys.stdout.write('# Terminating RTCDs.\n')
        admin.systemlauncher.exit_all_rtcs(package, verbose=verbose)
        admin.systemlauncher.terminate_system(package, verbose=verbose)
        return 0

    @manifest
    def download_profile(self, args):
        """ Run just one RTC and Show launched RTC profile.
        $ ./mgr.py rtc download_profile <RTC_NAME>
        """
        self.parser.add_option('-w', '--wakeuptimeout', help='Timeout of Sleep Function when waiting for the wakeup of RTC-Daemons',
                               default=5, dest='wakeuptimeout', action='store', type='float')
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag
        wakeuptimeout = options.wakeuptimeout

        wasanbon.arg_check(argv, 4)

        package = admin.package.get_package_from_path(os.getcwd())
        rtc = admin.rtc.get_rtc_from_package(package, argv[3], verbose=verbose)
        if self.run_rtc_in_package(package, rtc, verbose=verbose, background=True) != 0:
            return -1
        wasanbon.sleep(wakeuptimeout)
        rtcp = admin.rtcprofile.create_rtcprofile(rtc, verbose=verbose)
        print(admin.rtcprofile.tostring(rtcp))
        self.terminate_rtcd(package, verbose=verbose)
        return 0

    @manifest
    def verify_profile(self, args):
        """ Run just one RTC and compare the profile between the existing RTC.xml and launched RTC.
        $ ./mgr.py rtc verify_profile <RTC_NAME>
        """
        self.parser.add_option('-w', '--wakeuptimeout', help='Timeout of Sleep Function when waiting for the wakeup of RTC-Daemons',
                               default=5, dest='wakeuptimeout', action='store', type='float')
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag
        wakeuptimeout = options.wakeuptimeout

        wasanbon.arg_check(argv, 4)

        package = admin.package.get_package_from_path(os.getcwd())
        sys.stdout.write('# Starting RTC.\n')
        rtc = admin.rtc.get_rtc_from_package(package, argv[3], verbose=verbose)
        if self.run_rtc_in_package(package, rtc, verbose=verbose, background=True) != 0:
            return -1
        wasanbon.sleep(wakeuptimeout)
        sys.stdout.write('# Acquiring RTCProfile from Inactive RTC\n')
        rtcp = admin.rtcprofile.create_rtcprofile(rtc, verbose=verbose)
        self.terminate_rtcd(package, verbose=verbose)
        sys.stdout.write('# Comparing Acquired RTCProfile and Existing RTCProfile.\n')
        retval = admin.rtcprofile.compare_rtcprofile(rtc.rtcprofile, rtcp, verbose=verbose)
        if retval:
            sys.stdout.write('Failed.\n# RTCProfile must be updated.\n')
            return -1
        sys.stdout.write('Succeeded.\n# RTCProfile is currently matches to binary.\n')
        return 0

    @manifest
    def update_profile(self, args):
        """ Run just one RTC and compare the profile between the existing RTC.xml and launched RTC, then save RTC.xml.
        $ ./mgr.py rtc update_profile <RTC_NAME>
        """
        self.parser.add_option('-f', '--file', help='RTCProfile filename (default="RTC.xml")',
                               default='RTC.xml', dest='filename', action='store', type='string')
        self.parser.add_option('-d', '--dryrun', help='Just output on console', default=False, dest='dry_flag', action='store_true')
        self.parser.add_option('-w', '--wakeuptimeout', help='Timeout of Sleep Function when waiting for the wakeup of RTC-Daemons',
                               default=5, dest='wakeuptimeout', action='store', type='float')
        options, argv = self.parse_args(args[:], self._print_rtcs)
        verbose = options.verbose_flag
        dry = options.dry_flag
        filename = options.filename
        wakeuptimeout = options.wakeuptimeout

        wasanbon.arg_check(argv, 4)
        rtc_name = argv[3]

        package = admin.package.get_package_from_path(os.getcwd())
        sys.stdout.write('# Starting RTC.\n')
        rtc = admin.rtc.get_rtc_from_package(package, rtc_name, verbose=verbose)
        standalone = admin.systeminstaller.is_installed(package, rtc, standalone=True, verbose=verbose)
        if standalone:
            admin.systemlauncher.launch_standalone_rtc(package, rtc, stdout=True, verbose=verbose)
            pass
        else:
            if self.run_rtc_in_package(package, rtc, verbose=verbose, background=True) != 0:
                return -1
        wasanbon.sleep(wakeuptimeout)
        sys.stdout.write('# Acquiring RTCProfile from Inactive RTC\n')
        rtcp = admin.rtcprofile.create_rtcprofile(rtc, verbose=verbose)

        if standalone:
            pass
        else:
            self.terminate_rtcd(package, verbose=verbose)
        sys.stdout.write('# Comparing Acquired RTCProfile and Existing RTCProfile.\n')
        retval = admin.rtcprofile.compare_rtcprofile(rtc.rtcprofile, rtcp, verbose=verbose)
        if retval:
            filepath = os.path.join(rtc.path, filename)

            if not dry:
                outstr = admin.rtcprofile.tostring(retval, pretty_print=True)
                if outstr == None:
                    sys.stdout.write('# RTC Profile save failed.\n')
                    return -1
                if os.path.isfile(filepath):
                    f = filepath + wasanbon.timestampstr()
                    os.rename(filepath, f)
                    pass

                fout = open(filepath, 'w')
                fout.write(outstr)
                fout.close()
            else:
                sys.stdout.write(admin.rtcprofile.tostring(retval, pretty_print=True))

            sys.stdout.write('Succeed.\n')
            return 0
        sys.stdout.write('Succeed.\n')
        return 0