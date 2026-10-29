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
from pathlib import Path
import re
import shutil
import tempfile

ev = threading.Event()
endflag = False


class Plugin(PluginFunction):
    """ RT-Component / ROS package server management Plugin. """

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
    def check(self, args):
        """ Set .
        Server setting check.
        $ ./mgr.py server check <IP> <SYSTEM_FILENAME>
        """
    @manifest
    def ros(self, args):
        """ Set .
        ROS server setting.
        $ ./mgr.py server ros <IP>
        """

    @manifest
    def set(self, args):
        """ Set .
        $ Server settings.
        Usage:
        ./mgr.py server set \
            <SERVER_IP> \
            <LOCAL_IP> \
            <DOMAIN_ID> \
            [SYSTEM_FILENAME]
        SERVER_IP
            RTM NameServerを起動するPCのIP
        LOCAL_IP
            このPC自身のIP
            ROS1互換用として保持
        DOMAIN_ID
            ROS2で使用するROS_DOMAIN_ID
        SYSTEM_FILENAME
            RTM system XML名（必要な場合）
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
        # systemfile = options.systemfile # No longer an option
        plain = options.plain_flag
        quiet = options.quiet_flag

        # argv:
        # [0] mgr.py
        # [1] server
        # [2] set
        # [3] server_ip
        # [4] local_ip
        # [5] domain_id
        # [6] system_name (optional)
        wasanbon.arg_check(argv, 6)

        if plain:
            quiet = True

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
        middleware = None
        package_xml_dirs = self.find_package_xml(
            os.path.dirname(package.get_rtcpath()),
            'package.xml'
        )
        if package_xml_dirs:
            file_path = os.path.join(
                package_xml_dirs[0],
                "package.xml"
            )
            middleware = self.check_ros_buildtool(file_path)

        server_ip = argv[3]
        local_ip = argv[4]
        domain_id = argv[5]
        print(f"server_ip   : {server_ip}")
        print(f"local_ip    : {local_ip}")
        print(f"domain_id   : {domain_id}")
        print(f"middleware  : {middleware}")

        #ROS2
        if middleware == "ros2":
            self.update_ros2_settings(domain_id)
            print(
                f"[OK] ROS2 setting changed: "
                f"ROS_DOMAIN_ID={domain_id}"
            )
            return 0

        #ROS1 仮
        elif middleware == "ros1":
            self.update_ros1_settings(
                server_ip,
                local_ip=local_ip
            )
            print(
                "[OK] ROS1 setting changed"
            )
            return 0

        #RTM
        elif self.rtc_check=="ok":
            # systemfile_name = argv[4]
            # if not systemfile_name.endswith(".xml"):
            #     systemfile_name += ".xml"
            # systemfile = os.path.join(package.get_systempath(), systemfile_name)
            ##rtc_py.conf
            self.update_rtc_conf_ip("conf/rtc_py.conf", server_ip)

            ##siteinosystem.xml
            if len(argv) > 6:
                xml_file=argv[6]+".xml"
                self.update_rts_hosts_general(xml_file, server_ip, backup=True)
            print(
                f"[OK] RTM NameServer changed: "
                f"{server_ip}:2809"
            )
            return 0
        else:
            sys.stdout.write('## Not found Package\n')
            return -1

    def find_package_xml(self, directory, object):
        package_dirs = []
        for root, dirs, files in os.walk(directory):
            if object in files:
                package_dirs.append(root)
        return package_dirs

    #ROSミドルウェア判定
    def check_ros_buildtool(self, file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            buildtool_dependencies = root.findall(
                ".//buildtool_depend"
            )

            for dep in buildtool_dependencies:
                if dep.text is None:
                    continue
                buildtool = dep.text.strip()
                if buildtool == "catkin":
                    return "ros1"
                if buildtool in (
                    "ament_cmake",
                    "ament_python"
                ):
                    return "ros2"
            return None
        except ET.ParseError:
            return None
        except FileNotFoundError:
            return None

    def get_local_ip(self):
        """
         hostname -I からローカルIPを取得
        """
        try:
            result = subprocess.run(
                ["hostname", "-I"], capture_output=True, text=True, check=True
            )
            ip_list = result.stdout.strip().split()
            if ip_list:
                return ip_list[0]  # 最初のIPを返す
            else:
                raise RuntimeError("IPアドレスが取得できませんでした。")
        except Exception as e:
            raise RuntimeError(f"IPアドレス取得に失敗: {e}")

    def update_ros1_settings(self, master_ip, local_ip=None, bashrc_path=os.path.expanduser("~/.bashrc")):
        """
        ROS1互換用
        ~/.bashrc 内の ROS_MASTER_URI, ROS_IP, ROS_HOSTNAME を更新する関数
        - ROS_MASTER_URI は引数で指定
        - ROS_IP は引数で指定 (未指定なら ifconfig (hostname -I) で自動取得)
        - ROS_HOSTNAME は使わないので、あればコメントアウトする
        """
        if not local_ip:
            local_ip = self.get_local_ip()

        new_master = f'export ROS_MASTER_URI=http://{master_ip}:11311'
        new_ip     = f'export ROS_IP={local_ip}'

        with open(bashrc_path, "r") as f:
            lines = f.readlines()

        updated_lines = []
        for line in lines:
            if any(key in line for key in ["ROS_MASTER_URI", "ROS_IP", "ROS_HOSTNAME"]):
                if not line.strip().startswith("#"):
                    updated_lines.append("# " + line)
                else:
                    updated_lines.append(line)
            else:
                updated_lines.append(line)

        # 新しい設定を追記
        updated_lines.append("\n" + new_master + "\n")
        updated_lines.append(new_ip + "\n")

        with open(bashrc_path, "w") as f:
            f.writelines(updated_lines)

        print(f"[OK] ROS_MASTER_URI を {master_ip} に、ROS_IP を {local_ip} に更新しました。")

    def update_ros2_settings(self, domain_id, bashrc_path=os.path.expanduser("~/.bashrc")):
        """
        ~/.bashrc の ROS_DOMAIN_ID を更新する。
        既存の有効なROS_DOMAIN_IDはコメントアウトし、
        新しい設定を末尾へ追加する。
        """
        try:
            domain_id = int(domain_id)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid ROS_DOMAIN_ID: {domain_id}"
            )
        if domain_id < 0 or domain_id > 232:
            raise ValueError(
                f"ROS_DOMAIN_ID out of range: {domain_id}"
            )
        new_domain = (
            f"export ROS_DOMAIN_ID={domain_id}"
        )
        # .bashrcが無ければ作成
        if not os.path.exists(bashrc_path):
            Path(bashrc_path).touch()
        with open(
            bashrc_path,
            "r",
            encoding="utf-8"
        ) as f:
            lines = f.readlines()

        updated_lines = []
        for line in lines:
            # ROS_DOMAIN_IDだけを対象にする
            if "ROS_DOMAIN_ID" in line:
                if not line.strip().startswith("#"):
                    updated_lines.append(
                        "# " + line
                    )
                else:
                    updated_lines.append(line)
            else:
                updated_lines.append(line)
        updated_lines.append(
            "\n" + new_domain + "\n"
        )

        with open(
            bashrc_path,
            "w",
            encoding="utf-8"
        ) as f:
            f.writelines(updated_lines)

        # このmgr.pyプロセス自身にも反映
        os.environ["ROS_DOMAIN_ID"] = str(domain_id)
        print(
            f"[OK] ROS_DOMAIN_ID を "
            f"{domain_id} に更新しました。"
        )

    def update_rts_hosts_general(self, xml_path: str, new_ip: str, backup: bool = True):
        """
        XMLファイル内で以下を置換する:
        - rts:pathUri="HOST:PORT/..."
        - rtsExt:value="HOST:PORT/..."
        HOST部分を new_ip に変更
        """
        p = Path("system/" + xml_path)
        if not p.exists():
            raise FileNotFoundError(xml_path)

        text = p.read_text(encoding="utf-8")


        # rts:pathUri のホスト置換
        text = re.sub(
            r'(rts:pathUri=")[^":\s]+(?=:\d+/)',
            lambda m: f"{m.group(1)}{new_ip}",
            text
        )

        # rtsExt:value のホスト置換
        text = re.sub(
            r'(rtsExt:value=")[^":\s]+(?=:\d+/)',
            lambda m: f"{m.group(1)}{new_ip}",
            text
        )

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_name = tmp.name
        shutil.move(tmp_name, p)

        return f"[OK] Updated hosts in {xml_path} to {new_ip}"

    def update_rtc_conf_ip(self, conf_path: str, new_ip: str, backup: bool = True):
        path = Path(conf_path)
        if not path.exists():
            raise FileNotFoundError(conf_path)

        text = path.read_text(encoding="utf-8")

        # corba.nameservers: と :2809 の間を new_ip に置換
        text = re.sub(
            r'(corba\.nameservers\s*:\s*)([^:\s]*)(:2809)',
            lambda m: m.group(1) + new_ip + m.group(3),
            text
        )

        # ros.roscore.host= と & の間を new_ip に置換（& が無い場合は行末まで）
        text = re.sub(
            r'(ros\.roscore\.host=)[^&\s]*(?=&|$)',
            lambda m: m.group(1) + new_ip,
            text
        )

        # アトミックに書き換え
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_name = tmp.name
        os.replace(tmp_name, path)

        return f"[OK] Updated {conf_path} → corba.nameservers と ros.roscore.host を {new_ip} に設定しました"


