# Keypirinha launcher (keypirinha.com)

import keypirinha as kp
import keypirinha_util as kpu
import keypirinha_net as kpnet
import subprocess, json, re, urllib.parse

class vault(kp.Plugin):
    """
    Keypirinha plugin for accessing password/secret vaults.
    NOTE: must replace any <bracketed> strings before using


    More detailed documentation at: http://keypirinha.com/api/plugin.html
    TODO
    read exec to run from docs
    - add set timely expiry date
    """
    DEFAULT_ITEM_LABEL = "Vault Plugin"
    DEFAULT_ITEM_DESC = "Dummy text for vault record"
    KEYWORD = "Vault"
    DEFAULT_IDLE_TIME = 0.25
    ACTION_COPY_PASSWORD = "copy_password"
    ACTION_COPY_USERNAME = "copy_username"
    ACTION_COPY_URL = "copy_url"
    ACTION_COPY_HOST = "copy_host"
    ACTION_COPY_NOTES = "copy_notes"
    ITEMCAT_VAULT = kp.ItemCategory.USER_BASE + 1
    ITEMCAT_RESULT = kp.ItemCategory.USER_BASE + 2
    LOGIN_COMMAND="wsl lpass login --trust <login>"
    LOGOUT_COMMAND="wsl lpass logout"
    SYNC_COMMAND="wsl lpass sync"
    LOGIN_FZF_COMMAND="wsl lpass-copy-login"
    NOTES_FZF_COMMAND="wsl lpass-copy-notes"
    BW_FZF_COMMAND="wsl bw-copy"


    def __init__(self):
        super().__init__()
        self.records = []
        self.expression_items = []
        self._debug = False
        self.dbg("CONSTRUCTOR")
        self.idle_time = self.DEFAULT_IDLE_TIME

    def on_start(self):
        # load all items - view of name, username, url, source
        # Set hide console flag in py3.6: in py3.7 there's subprocess.CREATE_NO_WINDOW instead
        # TODO action/catalogue item: toggle copy/ability to copy/show permanently from each record's submenu
        # TODO check status action, run it on startup
        # TODO get domain name from url for dispaly
        # TODO display individual record values per action
        # TODO add keyword entry for search to copy username
        # TODO periodic signout (login is now trivial)
        # TODO get diffs on sync instead of whole batch

        # TODO cleanup repetition, category/targets
        # TODO cleanup command execution, make password manager agnostic
        # TODO change commands to only use pw-manage adapter
        actions = [
            self.create_action(
                name=self.ACTION_COPY_HOST,
                label="Copy host",
                short_desc="Copy host (url without http, slugs) to clipboard"),
            self.create_action(
                name=self.ACTION_COPY_PASSWORD,
                label="Copy password",
                short_desc="Copy password to clipboard"),
            self.create_action(
                name=self.ACTION_COPY_USERNAME,
                label="Copy username",
                short_desc="Copy username to clipboard"),
            self.create_action(
                name=self.ACTION_COPY_URL,
                label="Copy url",
                short_desc="Copy URL to clipboard"),
            self.create_action(
                name=self.ACTION_COPY_NOTES,
                label="Copy notes",
                short_desc="Copy notes to clipboard")
        ]
        self.set_actions(self.ITEMCAT_RESULT, actions)

    def on_catalog(self):
        # TODO find new stuff and merge in
        self.dbg("On Catalog")
        # self.set_catalog([self.create_item()])
        keyword_items = [self.create_item(
            category=kp.ItemCategory.KEYWORD,
            label=f"{self.DEFAULT_ITEM_LABEL}...",
            short_desc=self.DEFAULT_ITEM_DESC,
            target=self.KEYWORD,
            args_hint=kp.ItemArgsHint.REQUIRED,
            hit_hint=kp.ItemHitHint.NOARGS
            ),
            self.create_item(
                category=kp.ItemCategory.CMDLINE,
                label=f"{self.DEFAULT_ITEM_LABEL}: Login",
                short_desc=self.DEFAULT_ITEM_DESC,
                target=self.LOGIN_COMMAND,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
            ),
            self.create_item(
                category=kp.ItemCategory.CMDLINE,
                label=f"{self.DEFAULT_ITEM_LABEL}: Sync",
                short_desc=self.DEFAULT_ITEM_DESC,
                target=self.SYNC_COMMAND,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
            ),
            self.create_item(
                category=kp.ItemCategory.CMDLINE,
                label=f"{self.DEFAULT_ITEM_LABEL}: Logout",
                short_desc=self.DEFAULT_ITEM_DESC,
                target=self.LOGOUT_COMMAND,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
            ),
            self.create_item(
                category=kp.ItemCategory.CMDLINE,
                label=f"{self.DEFAULT_ITEM_LABEL}: Fzf Logins",
                short_desc=self.DEFAULT_ITEM_DESC,
                target=self.LOGIN_FZF_COMMAND,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
            ),
            self.create_item(
                category=kp.ItemCategory.CMDLINE,
                label=f"{self.DEFAULT_ITEM_LABEL}: Fzf Notes",
                short_desc=self.DEFAULT_ITEM_DESC,
                target=self.NOTES_FZF_COMMAND,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
            ),
            self.create_item(
                category=kp.ItemCategory.CMDLINE,
                label=f"{self.DEFAULT_ITEM_LABEL}: BW copy Fzf",
                short_desc=self.DEFAULT_ITEM_DESC,
                target=self.BW_FZF_COMMAND,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
            ),
        ]


        self.set_catalog(keyword_items)

    def on_events(self, flags):
        self.dbg("On event(s) (flags {:#x})".format(flags))
        if flags & kp.Events.PACKCONFIG:
            # self._read_config()
            self.on_catalog()

    def on_suggest(self, user_input, items_chain):
        # look in loaded records
        self.dbg("on suggest activate")
        self.dbg('On Suggest "{}" (items_chain[{}])'.format(user_input, len(items_chain)))

        self.dbg(f"items_chain[0]- category: {items_chain[0].category()}, target: {items_chain[0].target()}" if items_chain else "empty item chain")
        if (not items_chain
            or items_chain[0].category() != kp.ItemCategory.KEYWORD
            or items_chain[0].target() != self.KEYWORD):
            self.dbg("vault plugin not activated. exiting")
            return

        # avoid doing too much network requests in case user is still typing
        if self.should_terminate(self.idle_time):
            self.dbg("vault early exit")
            return

        # expression_items = list(
        #     map(lambda r: self._create_expression_item(self.DEFAULT_ITEM_LABEL, r), self.records))

        self.dbg(f"about to set suggestions, exp_item len: {len(self.expression_items)}")
        if self.expression_items:

            self.set_suggestions(self.expression_items, kp.Match.DEFAULT, kp.Sort.DEFAULT)

        # else:
        self.dbg("no records to list. no suggestions")


    def on_execute(self, item, action):
        self.dbg('On Execute "{}" (action: {} action.name: {})'.format(item, action, action.name() if action else ""))
        self.dbg(f'Item category: {item.category()}, target: {item.target()}, label: {item.label()}')
        if not item:
            return

        if (item.category() == kp.ItemCategory.CMDLINE \
            and (re.search(r"log(ged\s)*in", item.label().lower())
                or 'logout' in item.label().lower())):
            self.dbg(f'got a hit on cmdline category, about to run {item.target().split()}')
            self.expression_items = [self.create_item(
                category=kp.ItemCategory.ERROR,
                label=str(f"Process in progress..."),
                short_desc=str(f"Kicked off {item.target()}, hold on a moment!"),
                target="",
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
                )]

            self._wait_on_separate_subprocess(item.target().split())
            self.expression_items = [self.create_item(
                category=kp.ItemCategory.ERROR,
                label=str(f"Process complete: {item.target()}"),
                short_desc=str(f"Last finished running: {item.target()}!"),
                target="",
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
                )]

            # stdout, stderr = p.communicate()
            # self.dbg(f"Executed {item.target()} on {item}, got stdout {stdout}, stderr {stderr}")
            self.dbg(f"about to return from running {item.target().split()}")
            return

        if (item.category() == kp.ItemCategory.CMDLINE
            and 'sync' in item.label().lower()):
            self.dbg(f'got a hit on cmdline category, about to run {item.target().split()}')
            self._wait_on_separate_subprocess(item.target().split())
            self._populate_records()
            return

        if (item.category() == kp.ItemCategory.CMDLINE \
            and 'fzf' in item.label().lower()):
            self.dbg(f'got a hit on cmdline category, about to run {item.target().split()}')
            subprocess.check_call(item.target().split())
            return

        if item.category() != self.ITEMCAT_RESULT:
            return
        record = json.loads(item.data_bag())
        if action and action.name() in (self.ACTION_COPY_NOTES,
                                        self.ACTION_COPY_HOST,
                                        self.ACTION_COPY_URL,
                                        self.ACTION_COPY_USERNAME):

            if action.name() == self.ACTION_COPY_URL:
                kpu.set_clipboard(record['url'])
            elif action.name() == self.ACTION_COPY_HOST:
                host = urllib.parse.urlparse(record['url']).netloc
                kpu.set_clipboard(host)
            elif action.name() == self.ACTION_COPY_NOTES:
                kpu.set_clipboard(record['notes'])
            elif action.name() == self.ACTION_COPY_USERNAME:
                kpu.set_clipboard(record['username'])

        # elif action and action.name() in (self.ACTION_COPY_PASSWORD):
        else:
            kpu.set_clipboard(record['password'])
            # kpu.set_clipboard(self._get_field(record['id'], 'password'))
        # else:
            # kpu.set_clipboard(record['id'])
            # if using action menu, none doesn't fire - only one does
            # default no action: copy password (ACTION_COPY_RESULT)
            # actions = [
            #     self.create_action(
            #         name=self.ACTION_COPY_PASSWORD,
            #         label="Copy password",
            #         short_desc="Copy password to clipboard"),
            #     self.create_action(
            #         name=self.ACTION_COPY_USERNAME,
            #         label=str(f"Copy {record['username']}"),
            #         short_desc="Copy username to clipboard"),
            #     self.create_action(
            #         name=self.ACTION_COPY_URL,
            #         label=str(f"Copy {record['url']}"),
            #         short_desc="Copy URL to clipboard"),
            #     self.create_action(
            #         name=self.ACTION_COPY_NOTES,
            #         label=str(f"Copy {record['notes']}"),
            #         short_desc="Copy notes to clipboard") ]
            # self.set_actions(self.ITEMCAT_RESULT, actions)

    def on_activated(self):
        pass

    def on_deactivated(self):
        pass

    def _get_field(self, record_id, field):
        # TODO method call is super slow, ~7s - use this when fixed
        if self.should_terminate(self.idle_time):
            self.dbg("vault early exit")
            return

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self.dbg(f"about to to get field for id {record_id}, field: {field}")
        p = subprocess.Popen(["<path-to>/password-manager-adapter/src/Cli/bin/Release/netcoreapp2.2/win10-x64/Cli.exe", "get", record_id, field, "LastPass"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si)

        stdout, stderr = p.communicate()
        self.dbg(f"Attempt to get field for id {record_id}, {field}: {stdout}, stderr: {stderr}")

        return str(stdout, 'utf-8')


    def _copy_password(self, record_id):
        # TODO method call is super slow, ~7s - use this when fixed
        if self.should_terminate(self.idle_time):
            self.dbg("vault early exit")
            return

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self.dbg(f"about to to copy pw for id {record_id}")

        p = subprocess.Popen(["<path-to>/password-manager-adapter/src/Cli/bin/Release/netcoreapp2.2/win10-x64/Cli.exe", "get", "-c", record_id, 'password', "LastPass"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si)

        stdout, stderr = p.communicate()
        self.dbg(f"Attempt to copy pw for id {record_id}, stderr: {stderr}")


    def _create_expression_item(self, label, record):
        formatted_label = f"{label}: {record['name']} | {record['username']} | {record['url']} | {record['source']}",
        # self.dbg(f"About to create expression item with r label: {formatted_label}, json: {json.dumps(record)}")
        # label=f"{label}: {record}",
        return self.create_item(
            category=self.ITEMCAT_RESULT,
            label=str(formatted_label),
            short_desc=f"{label} (Press Enter to copy the result)",
            target=str(formatted_label),
            args_hint=kp.ItemArgsHint.FORBIDDEN,
            hit_hint=kp.ItemHitHint.IGNORE,
            data_bag=str(json.dumps(record))
            )

    def _get_records(self):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # TODO abstract into arbitrary executable for show related fields; set in config
        stdout = ""
        if self.should_terminate(self.idle_time):
            self.dbg("vault early exit inside get records")
            return

        self.expression_items = [self.create_item(
            category=kp.ItemCategory.ERROR,
            label=str(f"Fetch in progress..."),
            short_desc=str(f"Kicked off a fetch, hold on a moment!"),
            target="",
            args_hint=kp.ItemArgsHint.FORBIDDEN,
            hit_hint=kp.ItemHitHint.NOARGS
            )]

        try:
            self.dbg(f"updated item to in progress, about to fetch records in get_records")
            p = subprocess.Popen(["dotnet", "<path-to>/password-manager-adapter/src/Cli/bin/Debug/netcoreapp2.2/Cli.dll", "json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si)

            stdout, stderr = p.communicate()
            # self.dbg(f"parsed catalog on start: {self.records}")
            self.dbg(f"records parsed from get_records : {len(self.records)}, stderr: {stderr}")

            return (json.loads(stdout), stderr)
        except json.decoder.JSONDecodeError as error:
            self.dbg(f"decode error {error} occurred, output was: {stdout}")
            return ([], stdout)

    def _wait_on_separate_subprocess(self, args_list):
        p = subprocess.Popen(args_list)
        p.wait()

    def _populate_records(self):
        self.records, error = self._get_records()
        if self.should_terminate(self.idle_time):
            self.dbg("vault early exit inside populate records")
            return

        if error:
            self.dbg("Errored detected in populating, adding dud record")
            self.expression_items = [self.create_item(
                category=kp.ItemCategory.CMDLINE,
                label=str(f"Error fetching Vault records: {error}"),
                short_desc=str(f"Error occured. Hit enter to attempt a login."),
                target=self.LOGIN_COMMAND,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.NOARGS
                )]
            return

        self.expression_items = list(
            map(lambda r: self._create_expression_item(self.DEFAULT_ITEM_LABEL, r), self.records))


