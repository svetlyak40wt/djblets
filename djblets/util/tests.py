#
# tests.py -- Unit tests for classes in djblets.util
#
# Copyright (c) 2007-2009  Christian Hammond
# Copyright (c) 2007-2009  David Trowbridge
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

import datetime
import unittest

from django.conf import settings
from django.conf.urls import include, patterns, url
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.urlresolvers import NoReverseMatch, reverse
from django.http import HttpRequest
from django.template import Token, TOKEN_TEXT, TemplateSyntaxError
from django.utils import six
from django.utils.html import strip_spaces_between_tags

from djblets.cache.backend import (cache_memoize, make_cache_key,
                                  CACHE_CHUNK_SIZE)
from djblets.db.fields import JSONField
from djblets.testing.testcases import TestCase, TagTest
from djblets.urls.resolvers import DynamicURLResolver
from djblets.util.http import (get_http_accept_lists,
                               get_http_requested_mimetype,
                               is_mimetype_a)
from djblets.util.templatetags import (djblets_deco, djblets_email,
                                       djblets_utils)


def normalize_html(s):
    return strip_spaces_between_tags(s).strip()


class CacheTest(TestCase):
    def tearDown(self):
        cache.clear()

    def test_cache_memoize(self):
        """Testing cache_memoize"""
        cacheKey = "abc123"
        testStr = "Test 123"

        def cacheFunc(cacheCalled=[]):
            self.assertTrue(not cacheCalled)
            cacheCalled.append(True)
            return testStr

        result = cache_memoize(cacheKey, cacheFunc)
        self.assertEqual(result, testStr)

        # Call a second time. We should only call cacheFunc once.
        result = cache_memoize(cacheKey, cacheFunc)
        self.assertEqual(result, testStr)

    def test_cache_memoize_large_files(self):
        """Testing cache_memoize with large files"""
        cacheKey = "abc123"

        # This takes into account the size of the pickle data, and will
        # get us to exactly 2 chunks of data in cache.
        data = 'x' * (CACHE_CHUNK_SIZE * 2 - 8)

        def cacheFunc(cacheCalled=[]):
            self.assertTrue(not cacheCalled)
            cacheCalled.append(True)
            return data

        result = cache_memoize(cacheKey, cacheFunc, large_data=True,
                               compress_large_data=False)
        self.assertEqual(result, data)

        self.assertTrue(make_cache_key(cacheKey) in cache)
        self.assertTrue(make_cache_key('%s-0' % cacheKey) in cache)
        self.assertTrue(make_cache_key('%s-1' % cacheKey) in cache)
        self.assertFalse(make_cache_key('%s-2' % cacheKey) in cache)

        result = cache_memoize(cacheKey, cacheFunc, large_data=True,
                               compress_large_data=False)
        self.assertEqual(result, data)


class BoxTest(TagTest):
    def testPlain(self):
        """Testing box tag"""
        node = djblets_deco.box(self.parser, Token(TOKEN_TEXT, 'box'))
        context = {}

        self.assertEqual(normalize_html(node.render(context)),
                         '<div class="box-container"><div class="box">' +
                         '<div class="box-inner">\ncontent\n  ' +
                         '</div></div></div>')

    def testClass(self):
        """Testing box tag (with extra class)"""
        node = djblets_deco.box(self.parser, Token(TOKEN_TEXT, 'box "class"'))
        context = {}

        self.assertEqual(normalize_html(node.render(context)),
                         '<div class="box-container"><div class="box class">' +
                         '<div class="box-inner">\ncontent\n  ' +
                         '</div></div></div>')

    def testError(self):
        """Testing box tag (invalid usage)"""
        self.assertRaises(TemplateSyntaxError,
                          lambda: djblets_deco.box(
                              self.parser,
                              Token(TOKEN_TEXT, 'box "class" "foo"')))


class ErrorBoxTest(TagTest):
    def testPlain(self):
        """Testing errorbox tag"""
        node = djblets_deco.errorbox(self.parser,
                                     Token(TOKEN_TEXT, 'errorbox'))

        context = {}

        self.assertEqual(normalize_html(node.render(context)),
                         '<div class="errorbox">\ncontent\n</div>')

    def testId(self):
        """Testing errorbox tag (with id)"""
        node = djblets_deco.errorbox(self.parser,
                                     Token(TOKEN_TEXT, 'errorbox "id"'))

        context = {}

        self.assertEqual(normalize_html(node.render(context)),
                         '<div class="errorbox" id="id">\ncontent\n</div>')


    def testError(self):
        """Testing errorbox tag (invalid usage)"""
        self.assertRaises(TemplateSyntaxError,
                          lambda: djblets_deco.errorbox(
                              self.parser,
                              Token(TOKEN_TEXT, 'errorbox "id" "foo"')))


class HttpTest(TestCase):
    def setUp(self):
        self.request = HttpRequest()
        self.request.META['HTTP_ACCEPT'] = \
            'application/json;q=0.5,application/xml,text/plain;q=0.0,*/*;q=0.0'

    def test_http_accept_lists(self):
        """Testing djblets.http.get_http_accept_lists"""

        acceptable_mimetypes, unacceptable_mimetypes = \
            get_http_accept_lists(self.request)

        self.assertEqual(acceptable_mimetypes,
                         ['application/xml', 'application/json'])
        self.assertEqual(unacceptable_mimetypes, ['text/plain', '*/*'])

    def test_get_requested_mimetype_with_supported_mimetype(self):
        """Testing djblets.http.get_requested_mimetype with supported mimetype"""
        self.assertEqual(
            get_http_requested_mimetype(self.request, ['foo/bar',
                                                       'application/json']),
            'application/json')
        self.assertEqual(
            get_http_requested_mimetype(self.request, ['application/xml']),
            'application/xml')
        self.assertEqual(
            get_http_requested_mimetype(self.request, ['application/json',
                                                       'application/xml']),
            'application/xml')

    def test_get_requested_mimetype_with_no_consensus(self):
        """Testing djblets.http.get_requested_mimetype with no consensus between client and server"""
        self.request = HttpRequest()
        self.request.META['HTTP_ACCEPT'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'

        self.assertEqual(
            get_http_requested_mimetype(self.request, ['application/json',
                                                       'application/x-foo']),
            'application/json')

    def test_get_requested_mimetype_with_wildcard_supported_mimetype(self):
        """Testing djblets.http.get_requested_mimetype with supported */* mimetype"""
        self.request = HttpRequest()
        self.request.META['HTTP_ACCEPT'] = '*/*'
        self.assertEqual(
            get_http_requested_mimetype(self.request, ['application/json',
                                                       'application/xml']),
            'application/json')

    def test_get_requested_mimetype_with_unsupported_mimetype(self):
        """Testing djblets.http.get_requested_mimetype with unsupported mimetype"""
        self.assertEqual(
            get_http_requested_mimetype(self.request, ['text/plain']),
            None)
        self.assertEqual(
            get_http_requested_mimetype(self.request, ['foo/bar']),
            None)

    def test_is_mimetype_a(self):
        """Testing djblets.util.http.is_mimetype_a"""
        self.assertTrue(is_mimetype_a('application/json',
                                      'application/json'))
        self.assertTrue(is_mimetype_a('application/vnd.foo+json',
                                      'application/json'))
        self.assertFalse(is_mimetype_a('application/xml',
                                       'application/json'))
        self.assertFalse(is_mimetype_a('foo/vnd.bar+json',
                                       'application/json'))


class AgeIdTest(TagTest):
    def setUp(self):
        TagTest.setUp(self)

        self.now = datetime.datetime.utcnow()

        self.context = {
            'now':    self.now,
            'minus1': self.now - datetime.timedelta(1),
            'minus2': self.now - datetime.timedelta(2),
            'minus3': self.now - datetime.timedelta(3),
            'minus4': self.now - datetime.timedelta(4),
        }

    def testNow(self):
        """Testing ageid tag (now)"""
        self.assertEqual(djblets_utils.ageid(self.now), 'age1')

    def testMinus1(self):
        """Testing ageid tag (yesterday)"""
        self.assertEqual(djblets_utils.ageid(self.now - datetime.timedelta(1)),
                         'age2')

    def testMinus2(self):
        """Testing ageid tag (two days ago)"""
        self.assertEqual(djblets_utils.ageid(self.now - datetime.timedelta(2)),
                         'age3')

    def testMinus3(self):
        """Testing ageid tag (three days ago)"""
        self.assertEqual(djblets_utils.ageid(self.now - datetime.timedelta(3)),
                         'age4')

    def testMinus4(self):
        """Testing ageid tag (four days ago)"""
        self.assertEqual(djblets_utils.ageid(self.now - datetime.timedelta(4)),
                         'age5')

    def testNotDateTime(self):
        """Testing ageid tag (non-datetime object)"""
        class Foo:
            def __init__(self, now):
                self.day   = now.day
                self.month = now.month
                self.year  = now.year

        self.assertEqual(djblets_utils.ageid(Foo(self.now)), 'age1')


class TestEscapeSpaces(unittest.TestCase):
    def test(self):
        """Testing escapespaces filter"""
        self.assertEqual(djblets_utils.escapespaces('Hi there'),
                         'Hi there')
        self.assertEqual(djblets_utils.escapespaces('Hi  there'),
                         'Hi&nbsp; there')
        self.assertEqual(djblets_utils.escapespaces('Hi  there\n'),
                         'Hi&nbsp; there<br />')


class TestHumanizeList(unittest.TestCase):
    def test0(self):
        """Testing humanize_list filter (length 0)"""
        self.assertEqual(djblets_utils.humanize_list([]), '')

    def test1(self):
        """Testing humanize_list filter (length 1)"""
        self.assertEqual(djblets_utils.humanize_list(['a']), 'a')

    def test2(self):
        """Testing humanize_list filter (length 2)"""
        self.assertEqual(djblets_utils.humanize_list(['a', 'b']), 'a and b')

    def test3(self):
        """Testing humanize_list filter (length 3)"""
        self.assertEqual(djblets_utils.humanize_list(['a', 'b', 'c']),
                         'a, b and c')

    def test4(self):
        """Testing humanize_list filter (length 4)"""
        self.assertEqual(djblets_utils.humanize_list(['a', 'b', 'c', 'd']),
                         'a, b, c, and d')


class TestIndent(unittest.TestCase):
    def test(self):
        """Testing indent filter"""
        self.assertEqual(djblets_utils.indent('foo'), '    foo')
        self.assertEqual(djblets_utils.indent('foo', 3), '   foo')
        self.assertEqual(djblets_utils.indent('foo\nbar'),
                         '    foo\n    bar')


class QuotedEmailTagTest(TagTest):
    def testInvalid(self):
        """Testing quoted_email tag (invalid usage)"""
        self.assertRaises(TemplateSyntaxError,
                          lambda: djblets_email.quoted_email(self.parser,
                              Token(TOKEN_TEXT, 'quoted_email')))


class CondenseTagTest(TagTest):
    def getContentText(self):
        return "foo\nbar\n\n\n\n\n\n\nfoobar!"

    def test_plain(self):
        """Testing condense tag"""
        node = djblets_email.condense(self.parser,
                                      Token(TOKEN_TEXT, 'condense'))
        self.assertEqual(node.render({}), "foo\nbar\n\n\nfoobar!")

    def test_with_max_indents(self):
        """Testing condense tag with custom max_indents"""
        node = djblets_email.condense(self.parser,
                                      Token(TOKEN_TEXT, 'condense 1'))
        self.assertEqual(node.render({}), "foo\nbar\nfoobar!")


class QuoteTextFilterTest(unittest.TestCase):
    def testPlain(self):
        """Testing quote_text filter (default level)"""
        self.assertEqual(djblets_email.quote_text('foo\nbar'),
                         "> foo\n> bar")

    def testLevel2(self):
        """Testing quote_text filter (level 2)"""
        self.assertEqual(djblets_email.quote_text('foo\nbar', 2),
                         "> > foo\n> > bar")


class JSONFieldTests(unittest.TestCase):
    """Unit tests for JSONField."""

    def setUp(self):
        self.field = JSONField()

    def test_dumps_with_json_dict(self):
        """Testing JSONField with dumping a JSON dictionary"""
        result = self.field.dumps({'a': 1})
        self.assertTrue(isinstance(result, six.string_types))
        self.assertEqual(result, '{"a": 1}')

    def test_dumps_with_json_string(self):
        """Testing JSONField with dumping a JSON string"""
        result = self.field.dumps('{"a": 1, "b": 2}')
        self.assertTrue(isinstance(result, six.string_types))
        self.assertEqual(result, '{"a": 1, "b": 2}')

    def test_loading_json_dict(self):
        """Testing JSONField with loading a JSON dictionary"""
        result = self.field.loads('{"a": 1, "b": 2}')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('a' in result)
        self.assertTrue('b' in result)

    def test_loading_json_broken_dict(self):
        """Testing JSONField with loading a badly serialized JSON dictionary"""
        result = self.field.loads('{u"a": 1, u"b": 2}')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('a' in result)
        self.assertTrue('b' in result)

    def test_loading_json_array(self):
        """Testing JSONField with loading a JSON array"""
        result = self.field.loads('[1, 2, 3]')
        self.assertTrue(isinstance(result, list))
        self.assertEqual(result, [1, 2, 3])

    def test_loading_string(self):
        """Testing JSONField with loading a stored string"""
        result = self.field.loads('"foo"')
        self.assertTrue(isinstance(result, dict))
        self.assertEqual(result, {})

    def test_loading_broken_string(self):
        """Testing JSONField with loading a broken stored string"""
        result = self.field.loads('u"foo"')
        self.assertTrue(isinstance(result, dict))
        self.assertEqual(result, {})

    def test_loading_python_code(self):
        """Testing JSONField with loading Python code"""
        result = self.field.loads('locals()')
        self.assertTrue(isinstance(result, dict))
        self.assertEqual(result, {})

    def test_validate_with_valid_json_string(self):
        """Testing JSONField with validating a valid JSON string"""
        self.field.run_validators('{"a": 1, "b": 2}')

    def test_validate_with_invalid_json_string(self):
        """Testing JSONField with validating an invalid JSON string"""
        self.assertRaises(ValidationError,
                          lambda: self.field.run_validators('foo'))

    def test_validate_with_json_dict(self):
        """Testing JSONField with validating a JSON dictionary"""
        self.field.run_validators({'a': 1, 'b': 2})


class URLResolverTests(unittest.TestCase):
    def setUp(self):
        self._old_root_urlconf = settings.ROOT_URLCONF

    def tearDown(self):
        settings.ROOT_URLCONF = self._old_root_urlconf

    def test_dynamic_url_resolver(self):
        """Testing DynamicURLResolver"""
        self.dynamic_urls = DynamicURLResolver()

        settings.ROOT_URLCONF = patterns('',
            url(r'^root/', include(patterns('', self.dynamic_urls))),
            url(r'^foo/', self._dummy_view, name='foo'),
        )

        new_patterns = patterns('',
            url(r'^bar/$', self._dummy_view, name='bar'),
            url(r'^baz/$', self._dummy_view, name='baz'),
        )

        # The new patterns shouldn't reverse, just the original "foo".
        reverse('foo')
        self.assertRaises(NoReverseMatch, reverse, 'bar')
        self.assertRaises(NoReverseMatch, reverse, 'baz')

        # Add the new patterns. Now reversing should work.
        self.dynamic_urls.add_patterns(new_patterns)

        reverse('foo')
        reverse('bar')
        reverse('baz')

        # Get rid of the patterns again. We should be back in the original
        # state.
        self.dynamic_urls.remove_patterns(new_patterns)

        reverse('foo')
        self.assertRaises(NoReverseMatch, reverse, 'bar')
        self.assertRaises(NoReverseMatch, reverse, 'baz')

    def _dummy_view(self):
        pass
