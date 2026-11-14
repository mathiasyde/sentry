Java.perform(() => {
  const System = Java.use("java.lang.System");

  System.getenv.overload("java.lang.String").implementation = function (key) {
    if (key && key.toString() == "URL") {
      return "http://web/";
    }

    return this.getenv(key);
  };
});
