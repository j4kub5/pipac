pkgname=pipac
pkgver=0.1.0
pkgrel=1
pkgdesc="Maintain system based on package lists."
arch=('any')
url="https://github.com/j4kub5/pipac"
depends=('python')
optdepends=('yay: preferred AUR helper'
            'paru: alternative AUR helper')
source=("${pkgname}-${pkgver}.tar.gz::$url/archive/refs/tags/v${pkgver}.tar.gz")
sha256sums=('SKIP')

package() {
    cd "$srcdir/$pkgname-$pkgver"
    install -Dm755 pipac.py "$pkgdir/usr/bin/pipac"
}
