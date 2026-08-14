# DocFit visual renderer

This image is the only page renderer used by DocFit. It contains the locked
LibreOffice 25.2.3.2 build, Chinese locale, font aliases, and Poppler utilities.

Build it with:

```bash
docker build -t docfit-libreoffice-visual:25.2.3.2 docker/visual-renderer
```

The application starts every conversion with no network, a read-only root
filesystem, no Linux capabilities, `no-new-privileges`, an isolated temporary
HOME/profile, a read-only DOCX mount, and a separate writable output mount.
`packages.lock` is checked during the build; a repository update is required
when the Debian package set changes.
