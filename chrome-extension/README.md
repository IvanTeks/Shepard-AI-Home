# Shepard Chrome Bridge

1. Open `chrome://extensions` in Google Chrome.
2. Turn on **Developer mode**.
3. Choose **Load unpacked** and select this `chrome-extension` folder.
4. In Shepard, open **Connections**, choose the Chrome Bridge, and generate a pairing code.
5. Open the extension, paste that code, and choose **Save and test connection**.
6. On any normal webpage, open the extension and choose **Share current page**.
7. For a Wayfinder action, approve it in Shepard's Gatekeeper, reopen the
   extension, refresh **Approved actions**, and review/run the exact action.

The extension uses Manifest V3 `activeTab` access. It can read only the page on
which you explicitly invoke it. It does not request cookies, browsing history,
passwords, or persistent access to every site.

Approved navigation changes only the active tab. Approved form submission is a
separate two-step action: review the destination and field names, then check the
final confirmation box. Forms containing password, payment, banking, or identity
fields are blocked, as are ambiguous pages with multiple visible non-search forms.
