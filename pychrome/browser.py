#! /usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import requests

from .tab import Tab


__all__ = ["Browser"]


class Browser(object):
    _all_tabs = {}

    def __init__(self, url="http://127.0.0.1:9222"):
        self.dev_url = url
        self.context_ids = {}
        self._ws_api = None

        if self.dev_url not in self._all_tabs:
            self._tabs = self._all_tabs[self.dev_url] = {}
        else:
            self._tabs = self._all_tabs[self.dev_url]

    def _get_websocket_url(self):
        r = requests.get("%s/json/version" % self.dev_url)
        r.raise_for_status()
        version_data = r.json()
        return version_data['webSocketDebuggerUrl']

    @property
    def ws_api(self):
        """The main Websocket API connection."""
        if not self._ws_api:
            #
            # This object is just a websocket with event handling, not a new Tab.
            #
            self._ws_api = Tab(
                id='browser', type='browser', webSocketDebuggerUrl=self._get_websocket_url()
            )
            self._ws_api.start()
        return self._ws_api

    def new_tab(self, url=None, timeout=None):
        url = url or ''
        rp = requests.get("%s/json/new?%s" % (self.dev_url, url), json=True, timeout=timeout)
        tab = Tab(**rp.json())
        self._tabs[tab.id] = tab
        return tab

    def list_tab(self, timeout=None):
        rp = requests.get("%s/json" % self.dev_url, json=True, timeout=timeout)
        tabs_map = {}
        for tab_json in rp.json():
            if tab_json['type'] != 'page':  # pragma: no cover
                continue

            active_tab = tab_json['id'] in self._tabs
            if active_tab and self._tabs[tab_json['id']].status != Tab.status_stopped:
                tabs_map[tab_json['id']] = self._tabs[tab_json['id']]
            else:
                tabs_map[tab_json['id']] = Tab(**tab_json)

        self._tabs = tabs_map
        return list(self._tabs.values())

    def activate_tab(self, tab_id, timeout=None):
        if isinstance(tab_id, Tab):
            tab_id = tab_id.id

        rp = requests.get("%s/json/activate/%s" % (self.dev_url, tab_id), timeout=timeout)
        return rp.text

    def close_tab(self, tab_id, timeout=None):
        if isinstance(tab_id, Tab):
            tab_id = tab_id.id

        tab = self._tabs.pop(tab_id, None)

        if tab and tab_id in self.context_ids:
            self.ws_api.call_method(
                'Target.disposeBrowserContext',
                browserContextId=self.context_ids[tab_id]
            )

        if tab and tab.status == Tab.status_started:  # pragma: no cover
            tab.stop()

        rp = requests.get("%s/json/close/%s" % (self.dev_url, tab_id), timeout=timeout)
        return rp.text

    def version(self, timeout=None):
        rp = requests.get("%s/json/version" % self.dev_url, json=True, timeout=timeout)
        return rp.json()

    def __str__(self):
        return '<Browser %s>' % self.dev_url

    def new_private_tab(self, timeout=None):
        """Create a new tab in a new browser context.

        This tab will be isolated from other tabs.

        https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-createBrowserContext

        :param timeout: The timeout for API calls.
        :rtype: Tab
        """
        context = self.ws_api.Target.createBrowserContext(_timeout=timeout)
        try:
            context_id = context['browserContextId']
        except KeyError:
            raise RuntimeError("Can't create a new private context.")

        target = self.ws_api.Target.createTarget(
            url='about:blank', browserContextId=context_id, _timeout=timeout
        )

        self.list_tab(timeout=timeout)

        if target['targetId'] in self._tabs:
            tab = self._tabs[target['targetId']]
            tab.context_id = context_id
            self.context_ids[tab.id] = context_id
        else:
            raise RuntimeError("Failed to create a new private tab: %s" % target['targetId'])
        return tab

    def __del__(self):
        self.ws_api.stop()

    __repr__ = __str__
