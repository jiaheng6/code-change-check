import javascript

from CallExpr call
where call.getFile().getRelativePath() != ""
select
  call.getFile().getRelativePath(),
  call.getStartLine(),
  call.getCallee().toString(),
  call.getNumArgument()
