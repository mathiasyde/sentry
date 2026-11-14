// native: WebView permission hooks: chrome-client permission prompts and PermissionRequest grant/deny.
function hookChromeClientPermissions(ctx, ChromeClientClass, className) {
  const {
    hookMethod,
    stringValue,
    log,
  } = ctx;

    hookMethod(
      ChromeClientClass,
      "onPermissionRequest",
      ["android.webkit.PermissionRequest"],
      (overload) =>
        function (request) {
          log(EVENT_TYPE.PERMISSION_REQUESTED, {
            chromeClientClass: className,
            origin: request ? stringValue(request.getOrigin()) : null,
            resources: request ? request.getResources() : [],
          });

          return overload.apply(this, arguments);
        },
    );

    hookMethod(
      ChromeClientClass,
      "onGeolocationPermissionsShowPrompt",
      ["java.lang.String", "android.webkit.GeolocationPermissions$Callback"],
      (overload) =>
        function (origin, callback) {
          log(EVENT_TYPE.PERMISSION_REQUESTED, {
            chromeClientClass: className,
            type: "geolocation",
            origin: stringValue(origin),
            callback: callback,
          });

          return overload.apply(this, arguments);
        },
    );
}

function installPermissionHooks(ctx) {
  const {
    PermissionRequest,
    stringValue,
    log,
  } = ctx;

  const permissionGrant = PermissionRequest.grant.overload(
    "[Ljava.lang.String;",
  );
  permissionGrant.implementation = function (resources) {
    log(EVENT_TYPE.PERMISSION_GRANT_CALLED, {
      origin: stringValue(this.getOrigin()),
      resources: resources,
    });

    return permissionGrant.apply(this, arguments);
  };

  const permissionDeny = PermissionRequest.deny.overload();
  permissionDeny.implementation = function () {
    log(EVENT_TYPE.PERMISSION_DENY_CALLED, {
      origin: stringValue(this.getOrigin()),
      resources: this.getResources(),
    });

    return permissionDeny.apply(this, arguments);
  };
}
