# Copyright (c) The OpenTracing Authors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from threading import Lock
import time

import opentracing
from opentracing import Format, Tracer
from opentracing import UnsupportedFormatException

from .context import SpanContext
from .span import MockSpan


class MockTracer(Tracer):

    def __init__(self):
        """Initialize a MockTracer instance.

        By default, MockTracer registers propagators for Format.TEXT_MAP,
        Format.HTTP_HEADERS and Format.BINARY. The user should call
        register_propagator() for each additional inject/extract format.
        """

        super(MockTracer, self).__init__()
        self._propagators = {}
        self._finished_spans = []
        self._spans_lock = Lock()

        # Simple-as-possible (consecutive for repeatability) id generation.
        self._next_id = 0
        self._next_id_lock = Lock()

        self._register_required_propagators()

    def register_propagator(self, format, propagator):
        """Register a propagator with this MockTracer.

        :param string format: a Format identifier like Format.TEXT_MAP
        :param Propagator propagator: a Propagator instance to handle
            inject/extract calls involving `format`
        """
        self._propagators[format] = propagator

    def _register_required_propagators(self):
        from .text_propagator import TextPropagator
        from .binary_propagator import BinaryPropagator
        self.register_propagator(Format.TEXT_MAP, TextPropagator())
        self.register_propagator(Format.HTTP_HEADERS, TextPropagator())
        self.register_propagator(Format.BINARY, BinaryPropagator())

    def finished_spans(self):
        with self._spans_lock:
            return list(self._finished_spans)

    def reset(self):
        with self._spans_lock:
            self._finished_spans = []

    def _append_finished_span(self, span):
        with self._spans_lock:
            self._finished_spans.append(span)

    def _generate_id(self):
        with self._next_id_lock:
            self._next_id += 1
            return self._next_id

    def start_span(self,
                   operation_name=None,
                   child_of=None,
                   references=None,
                   tags=None,
                   start_time=None,
                   ignore_active_span=False):

        start_time = time.time() if start_time is None else start_time

        # See if we have a parent_ctx in `references`
        parent_ctx = None
        if child_of is not None:
            parent_ctx = (
                child_of if isinstance(child_of, opentracing.SpanContext)
                else child_of.context)
        elif references is not None and len(references) > 0:
            # TODO only the first reference is currently used
            parent_ctx = references[0].referenced_context

        # Assemble the child ctx
        ctx = SpanContext(span_id=self._generate_id())
        if parent_ctx is not None:
            if parent_ctx._baggage is not None:
                ctx._baggage = parent_ctx._baggage.copy()
            ctx.trace_id = parent_ctx.trace_id
        else:
            ctx.trace_id = self._generate_id()

        # Tie it all together
        return MockSpan(
            self,
            operation_name=operation_name,
            context=ctx,
            parent_id=(None if parent_ctx is None else parent_ctx.span_id),
            tags=tags,
            start_time=start_time)

    def inject(self, span_context, format, carrier):
        if format in self._propagators:
            self._propagators[format].inject(span_context, carrier)
        else:
            raise UnsupportedFormatException()

    def extract(self, format, carrier):
        if format in self._propagators:
            return self._propagators[format].extract(carrier)
        else:
            raise UnsupportedFormatException()
