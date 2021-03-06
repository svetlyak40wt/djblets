#
# hooks.py -- Common extension hook points.
#
# Copyright (c) 2010-2011  Beanbag, Inc.
# Copyright (c) 2008-2010  Christian Hammond
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals

from django.core.urlresolvers import NoReverseMatch, reverse
from django.template.loader import render_to_string

from djblets.util.compat import six


class ExtensionHook(object):
    """The base class for a hook into some part of the project.

    ExtensionHooks are classes that can hook into an
    :py:class:`ExtensionHookPoint` to provide some level of functionality
    in a project. A project should provide a subclass of ExtensionHook that
    will provide functions for getting data or anything else that's needed,
    and then extensions will subclass that specific ExtensionHook.

    A base ExtensionHook subclass must use :py:class:`ExtensionHookPoint`
    as a metaclass. For example::

        from djblets.util.compat import six

        @six.add_metaclass(ExtensionHookPoint)
        class NavigationHook(ExtensionHook):
    """
    def __init__(self, extension):
        self.extension = extension
        self.extension.hooks.add(self)
        self.__class__.add_hook(self)

    def shutdown(self):
        self.__class__.remove_hook(self)


class ExtensionHookPoint(type):
    """A metaclass used for base Extension Hooks.

    Base :py:class:`ExtensionHook` classes use :py:class:`ExtensionHookPoint`
    as a metaclass. This metaclass stores the list of registered hooks that
    an :py:class:`ExtensionHook` will automatically register with.
    """
    def __init__(cls, name, bases, attrs):
        super(ExtensionHookPoint, cls).__init__(name, bases, attrs)

        if not hasattr(cls, "hooks"):
            cls.hooks = []

    def add_hook(cls, hook):
        """Adds an ExtensionHook to the list of active hooks.

        This is called automatically by :py:class:`ExtensionHook`.
        """
        cls.hooks.append(hook)

    def remove_hook(cls, hook):
        """Removes an ExtensionHook from the list of active hooks.

        This is called automatically by :py:class:`ExtensionHook`.
        """
        cls.hooks.remove(hook)


@six.add_metaclass(ExtensionHookPoint)
class URLHook(ExtensionHook):
    """Custom URL hook.

    A hook that installs custom URLs. These URLs reside in a project-specified
    parent URL.
    """
    def __init__(self, extension, patterns):
        super(URLHook, self).__init__(extension)
        self.patterns = patterns
        self.dynamic_urls = self.extension.extension_manager.dynamic_urls
        self.dynamic_urls.add_patterns(patterns)

    def shutdown(self):
        super(URLHook, self).shutdown()

        self.dynamic_urls.remove_patterns(self.patterns)


@six.add_metaclass(ExtensionHookPoint)
class TemplateHook(ExtensionHook):
    """Custom templates hook.

    A hook that renders a template at hook points defined in another template.
    """
    _by_name = {}

    def __init__(self, extension, name, template_name=None, apply_to=[]):
        super(TemplateHook, self).__init__(extension)
        self.name = name
        self.template_name = template_name
        self.apply_to = apply_to

        if not name in self.__class__._by_name:
            self.__class__._by_name[name] = [self]
        else:
            self.__class__._by_name[name].append(self)

    def shutdown(self):
        super(TemplateHook, self).shutdown()

        self.__class__._by_name[self.name].remove(self)

    def render_to_string(self, request, context):
        """Renders the content for the hook.

        By default, this renders the provided template name to a string
        and returns it.
        """
        context.push()
        context['extension'] = self.extension

        try:
            return render_to_string(self.template_name, context)
        finally:
            context.pop()

    def applies_to(self, context):
        """Returns whether or not this TemplateHook should be applied given the
        current context.
        """

        # If apply_to is empty, this means we apply to all - so
        # return true
        if not self.apply_to:
            return True

        # Extensions Middleware stashes the kwargs into the context
        kwargs = context['request']._djblets_extensions_kwargs
        current_url = context['request'].path_info

        # For each URL name in apply_to, check to see if the reverse
        # URL matches the current URL.
        for applicable in self.apply_to:
            try:
                reverse_url = reverse(applicable, args=(), kwargs=kwargs)
            except NoReverseMatch:
                # It's possible that the URL we're reversing doesn't take
                # any arguments.
                try:
                    reverse_url = reverse(applicable)
                except NoReverseMatch:
                    # No matches here, move along.
                    continue

            # If we got here, we found a reversal.  Let's compare to the
            # current URL
            if reverse_url == current_url:
                return True

        return False

    @classmethod
    def by_name(cls, name):
        return cls._by_name.get(name, [])
